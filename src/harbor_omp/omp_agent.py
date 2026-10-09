"""The omp Harbor agent.

``OmpAgent`` installs the pinned omp CLI with bun and runs one trial with it::

    omp -p --auto-approve <run_flags> --session-dir=<logs>/omp-sessions \\
        --model=<provider/model> [--thinking=<level>] <instruction>

The agent runs as the environment's agent user under an isolated config home
(``HOME=<config_home> PI_CONFIG_DIR=.omp``). The agent resets that home on
every install and fills it from ``seed``, from a shipped config checkout, and
from the plugin it installs — so what a trial ran with is what the agent put
there, never what the image happened to carry.

What the run leaves behind: the exact argv in
``/logs/agent/resolved/run-flags.json`` before omp launches (and also in an
install-only trial), the combined agent output in ``<logs>/omp.txt``, and the
session JSONL under ``<logs>/omp-sessions`` — summed back into ``AgentContext``
after the run.

Nothing in this module reads a benchmark, a profile, or a harness module. The
extension points in ``harbor_omp.hooks`` are how a consumer adds files and
commands; everything profile-shaped (benchmark names, scan lists, evidence
collectors, toolchain probes) arrives through them.

What a run leaves behind besides that: the ATIF trajectory at
``<logs>/trajectory.json``, written after the run by
``populate_context_post_run`` and, in a streaming job, kept current while the
run is going by Harbor's ``sync_trajectory`` polling ``convert_trajectory``.
Both paths build it with ``harbor_omp.trajectory`` — one converter, one session
reader — and the trajectory's totals are the same numbers the context reports.

Known gaps, stated rather than implied: no resume/load/handoff, no skills or MCP
seam, and no per-exec timeout. See the README and ``docs/architecture.md``.
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final, override

from harbor.agents.capabilities import AgentCapabilities
from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.agents.model_connection import ModelConnectionSpec
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trajectories import Trajectory
from pydantic import ValidationError

from harbor_omp import hooks, install, session, trajectory
from harbor_omp.options import MINIMAL_EXTENSIONS_FLAGS, OmpOptions, package_spec

# ---------------------------------------------------------------------------
# Container paths. Everything the agent writes lives under /tmp or under the
# environment log dir, so a trial never touches the task workspace except
# through the agent itself.
# ---------------------------------------------------------------------------

#: The shipped plugin: tar, then the extracted checkout the install reads.
PLUGIN_TAR: Final[PurePosixPath] = PurePosixPath("/tmp/harbor-omp-plugin.tar")
PLUGIN_DIR: Final[PurePosixPath] = PurePosixPath("/tmp/harbor-omp-plugin")

#: The shipped config content: tar (extracted after the home reset).
CONFIG_TAR: Final[PurePosixPath] = PurePosixPath("/tmp/harbor-omp-config.tar")

#: Staging dir for the seed files (outside the config home, so the home reset
#: never wipes them before they are copied in).
SEED_DIR: Final[PurePosixPath] = PurePosixPath("/tmp/harbor-omp-seed")

#: The argv the agent ran, recorded before omp launches.
RUN_FLAGS_RECORD: Final[PurePosixPath] = install.RESOLVED_DIR / "run-flags.json"
#: Which plugin source (commit, host path) the trial installed.
PLUGIN_SOURCE_RECORD: Final[PurePosixPath] = install.RESOLVED_DIR / "plugin-source.json"
#: Which config content (commit, host path, paths) the trial shipped.
CONFIG_SOURCE_RECORD: Final[PurePosixPath] = install.RESOLVED_DIR / "config-source.json"

#: The config dir name under the isolated home (omp reads it via PI_CONFIG_DIR).
CONFIG_DIR_NAME: Final[str] = ".omp"

#: Harbor's workspace dir, and the cwd the agent and the hooks share.
WORKSPACE_DIR: Final[str] = "/app"


def archive_git_head(
    src: Path, *, what: str, pathspecs: Sequence[str] | None = None
) -> tuple[str, bytes]:
    """Verify a git checkout is clean and archive its committed HEAD.

    Pre: ``src`` is a HOST path meant to be shipped into a container (no host
    mounts); ``pathspecs`` restricts the archive to those repo-relative paths
    (None archives the whole tree). Post: returns ``(commit, tar_bytes)`` where
    the tar holds exactly the committed content of the requested paths.

    Raises:
        ValueError: When ``src`` is not a git work tree, when the shipped paths
            have uncommitted changes to tracked files, when a pathspec matches
            nothing at HEAD, or when git fails — the pinned content would not be
            what runs, so a caller must abort before any upload or model spend.
    """

    def _abort(reason: str) -> ValueError:
        return ValueError(
            f"{reason}; the trial aborts before any upload and before any model spend"
        )

    def _git(*args: str, text: bool = True) -> subprocess.CompletedProcess[Any]:
        return subprocess.run(["git", "-C", str(src), *args], capture_output=True, text=text)

    probe = _git("rev-parse", "--is-inside-work-tree")
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        detail = (probe.stderr or probe.stdout).strip() or "git failed"
        raise _abort(f"{what} source {src} is not a git work tree ({detail})")

    status_args = ("status", "--porcelain", "--untracked-files=no")
    if pathspecs is not None:
        status_args += ("--", *pathspecs)
    dirty = _git(*status_args)
    if dirty.returncode != 0:
        raise _abort(
            f"git status failed in {what} source {src}: {(dirty.stderr or dirty.stdout).strip()}"
        )
    if dirty.stdout.strip():
        raise _abort(
            f"{what} source {src} has uncommitted changes to tracked files; "
            "the pinned content would not be what runs:\n"
            f"{dirty.stdout.strip()}"
        )

    commit = _git("rev-parse", "HEAD")
    if commit.returncode != 0:
        raise _abort(
            f"git rev-parse HEAD failed in {what} source {src}: "
            f"{(commit.stderr or commit.stdout).strip()}"
        )
    commit_sha = commit.stdout.strip()

    if pathspecs is not None:
        listing = _git("ls-tree", "-r", "--name-only", "HEAD", "--", *pathspecs)
        if listing.returncode != 0:
            raise _abort(
                f"git ls-tree failed in {what} source {src}: "
                f"{(listing.stderr or listing.stdout).strip()}"
            )
        at_head = listing.stdout.splitlines()
        missing = []
        for pathspec in pathspecs:
            # A directory pathspec may carry a trailing slash; git archive
            # accepts either form, so the presence check must too.
            prefix = pathspec.rstrip("/")
            if not any(name == prefix or name.startswith(prefix + "/") for name in at_head):
                missing.append(pathspec)
        if missing:
            raise _abort(
                f"{what} source {src} is missing pinned paths at HEAD "
                f"{commit_sha[:12]}: {', '.join(missing)}"
            )

    archive_args = ("archive", "--format=tar", "HEAD")
    if pathspecs is not None:
        archive_args += ("--", *pathspecs)
    archived = _git(*archive_args, text=False)
    if archived.returncode != 0:
        raise _abort(
            f"git archive failed in {what} source {src}: "
            f"{archived.stderr.decode(errors='replace').strip()}"
        )
    return commit_sha, archived.stdout


async def _upload_json_record(
    environment: BaseEnvironment, record: Mapping[str, object], target: PurePosixPath
) -> None:
    """Upload a JSON provenance record into the container's resolved dir."""

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".json", delete=False, newline="\n"
    ) as record_file:
        json.dump(record, record_file, indent=2)
        record_path = Path(record_file.name)
    try:
        await environment.upload_file(record_path, target.as_posix())
    finally:
        record_path.unlink(missing_ok=True)


async def _upload_tar_bytes(
    environment: BaseEnvironment, tar_bytes: bytes, target: PurePosixPath
) -> None:
    """Upload an in-memory tar into the container."""

    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tar_file:
        tar_file.write(tar_bytes)
        tar_path = Path(tar_file.name)
    try:
        await environment.upload_file(tar_path, target.as_posix())
    finally:
        tar_path.unlink(missing_ok=True)


def _setting_value(value: object) -> str:
    """A plugin setting as omp's ``plugin config set`` argument."""

    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


class OmpAgent(BaseInstalledAgent):
    """omp (oh-my-pi) as a Harbor installed agent.

    Install: bun, then the pinned omp dist, then the extra files, then the
    isolated config home (a reset, the seed, the shipped config content, the
    plugin). Run: the argv the options describe, under the isolated home, with
    the extension-point commands around it. Report: the session JSONL summed
    into ``AgentContext``.

    ``version()`` reports the version the container measured with
    ``omp --version``, not the pin: the pin is ``options.version`` and is what
    the install command installs, recorded with the argv in ``run-flags.json``.
    """

    # ATIF is the one capability this agent implements; every other flag stays
    # false because Harbor gates on it, and a flag turned on without the
    # behaviour behind it is a silent gap. ``atif`` is true because
    # ``convert_trajectory`` builds a validated trajectory and
    # ``populate_context_post_run`` writes one.
    capabilities = AgentCapabilities(atif=True)
    MODEL_CONNECTION = ModelConnectionSpec(passthrough=True)

    options_model = OmpOptions
    options: OmpOptions

    _OUTPUT_FILENAME = "omp.txt"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Harbor reads ``options.version`` as the *reported* agent version too,
        # which would stop ``setup()`` from probing the CLI that actually
        # landed. The option is this agent's install pin; the report is the
        # measured ``omp --version`` output, so the pin is never claimed as a
        # verified version.
        self._version = None

    # ------------------------------------------------------------------
    # Identity and version
    # ------------------------------------------------------------------
    @staticmethod
    @override
    def name() -> str:
        return "omp"

    @override
    def get_version_command(self) -> str | None:
        return install.version_command()

    @override
    def parse_version(self, stdout: str) -> str:
        return install.parse_version(stdout)

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------
    @override
    async def install(self, environment: BaseEnvironment) -> None:
        # The install must name its package before anything reaches the
        # container: a blank or malformed version is a caller error, not a
        # reason to spend container commands on nothing.
        spec = package_spec(self.options.version)
        # Any source that cannot be pinned aborts here, before any upload and
        # before any model spend.
        if self.options.plugin is not None:
            await self._ship_plugin(environment)
        if self.options.config_source is not None:
            await self._ship_config(environment)

        await self.ensure_system_dependencies(environment, install.SYSTEM_DEPENDENCIES)
        await self.exec_as_agent(
            environment,
            command=install.install_command(
                spec,
                directories=(
                    self.environment_logs_dir / self.options.session_dir_name,
                    install.RESOLVED_DIR,
                ),
            ),
        )
        await self._upload_extra_files(environment)
        await self._prepare_config_home(environment)

    async def _ship_plugin(self, environment: BaseEnvironment) -> None:
        """Ship the plugin source: verify, archive HEAD, upload, extract.

        Pre: ``plugin`` names a host git checkout. Post: the committed HEAD is
        extracted at ``PLUGIN_DIR`` as the agent user, and the source record
        names the plugin, commit and host path the trial shipped.

        Raises:
            ValueError: When the plugin has no name or no source, or the source
                cannot be pinned — before any upload.
        """

        plugin = self.options.plugin or {}
        name = str(plugin.get("name") or "").strip()
        if not name:
            raise ValueError(
                "plugin is set but plugin.name is unset; the config-home step "
                "cannot enable a plugin it cannot name; the trial aborts before "
                "any upload and before any model spend"
            )
        src_value = plugin.get("src")
        if not src_value:
            raise ValueError(
                "plugin is set but plugin.src is unset (a HOST path to a git "
                "checkout of the plugin); the trial aborts before any upload "
                "and before any model spend"
            )
        src = Path(str(src_value)).expanduser()
        commit, tar_bytes = archive_git_head(src, what="the plugin source")
        await _upload_tar_bytes(environment, tar_bytes, PLUGIN_TAR)
        # Extraction runs as the agent user so the config-home step (also the
        # agent user) can read the plugin, and the resolved dir exists before
        # the source record lands in it.
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                f"rm -rf {PLUGIN_DIR.as_posix()} && "
                f"mkdir -p {PLUGIN_DIR.as_posix()} "
                f"{install.RESOLVED_DIR.as_posix()} && "
                f"tar -xf {PLUGIN_TAR.as_posix()} -C {PLUGIN_DIR.as_posix()}"
            ),
        )
        await _upload_json_record(
            environment,
            {"name": name, "commit": commit, "src": str(src)},
            PLUGIN_SOURCE_RECORD,
        )

    async def _ship_config(self, environment: BaseEnvironment) -> None:
        """Ship config content: verify, archive HEAD of exactly ``config_paths``.

        Pre: ``config_source`` is a host git checkout and ``config_paths`` names
        repo-relative paths in it. Post: the tar sits at ``CONFIG_TAR`` ready to
        extract, and the source record names the commit, host path and paths.
        The extract itself runs after the config home is reset
        (``_prepare_config_home``), so the shipped content survives the reset.

        Raises:
            ValueError: When the source or the path list is missing/empty, or
                the source cannot be pinned — before any upload.
        """

        src_value = self.options.config_source
        if not src_value:
            raise ValueError(
                "config_source is blank; a config ship needs a HOST path to a "
                "git checkout, or must be left unset"
            )
        paths = [str(path) for path in self.options.config_paths or []]
        if not paths:
            raise ValueError(
                "config_source is set but config_paths is empty; a config ship "
                "that names no paths would silently ship nothing, so the trial "
                "aborts before any upload and before any model spend"
            )
        src = Path(str(src_value)).expanduser()
        commit, tar_bytes = archive_git_head(src, what="the config content", pathspecs=paths)
        await self.exec_as_agent(
            environment,
            command=f"mkdir -p {install.RESOLVED_DIR.as_posix()}",
        )
        await _upload_tar_bytes(environment, tar_bytes, CONFIG_TAR)
        await _upload_json_record(
            environment,
            {"commit": commit, "src": str(src), "paths": paths},
            CONFIG_SOURCE_RECORD,
        )

    async def _upload_extra_files(self, environment: BaseEnvironment) -> None:
        """Upload the extension point's host files, or fail loudly.

        Raises:
            ValueError: When a named host path is not a readable file — a hook
                that silently received nothing is worse than a failed setup.
        """

        for host, container in self.options.extra_files or ():
            source = Path(str(host)).expanduser()
            if not source.is_file():
                raise ValueError(
                    f"extra_files names {source}, which is not a readable file; "
                    "the trial aborts before any model spend"
                )
            await environment.upload_file(source, PurePosixPath(str(container)).as_posix())

    # ------------------------------------------------------------------
    # The isolated config home
    # ------------------------------------------------------------------
    @property
    def _config_home(self) -> str:
        """The isolated HOME the agent runs under."""

        return str(self.options.config_home)

    @property
    def _config_dir(self) -> PurePosixPath:
        """The config dir omp reads: ``<config_home>/.omp`` with PI_CONFIG_DIR."""

        return PurePosixPath(self._config_home) / CONFIG_DIR_NAME

    async def _prepare_config_home(self, environment: BaseEnvironment) -> None:
        """Reset the home, land the seed, install the plugin, extract the config.

        The reset always runs, so a trial never inherits content from an image
        or a previous attempt. The seed is uploaded before the reset (to
        ``SEED_DIR``, outside the home) and copied in after it; the shipped
        config tar is extracted after the plugin install, so both survive.
        """

        if self.options.seed:
            await self._upload_seed(environment)
        await self.exec_as_agent(environment, command=self._config_home_command())
        if self.options.config_source is not None:
            await self.exec_as_agent(environment, command=self._config_extract_command())

    async def _upload_seed(self, environment: BaseEnvironment) -> None:
        """Write the seed files to the staging dir, one upload per file.

        Raises:
            ValueError: When a seed path is absolute, escapes the config dir,
                or uses backslash separators — an upload target a caller did
                not mean is a silent misconfig, not a convenience.
        """

        seed = dict(self.options.seed or {})
        staging = Path(tempfile.mkdtemp(prefix="harbor-omp-seed-"))
        try:
            for relpath in sorted(seed):
                pure = PurePosixPath(relpath)
                if "\\" in relpath or pure.is_absolute() or ".." in pure.parts:
                    raise ValueError(
                        f"seed path {relpath!r} must be a relative POSIX path "
                        "inside the config dir (no backslashes, no '..')"
                    )
                if str(pure) in ("", "."):
                    continue
                local = staging / pure
                local.parent.mkdir(parents=True, exist_ok=True)
                # Bytes, not text: a seed written through the host's newline
                # translation would reach the container changed.
                local.write_bytes(seed[relpath].encode("utf-8"))
                await environment.upload_file(local, (SEED_DIR / pure).as_posix())
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _config_home_command(self) -> str:
        """The in-container config-home step (strict).

        Resets the home, copies the seed in when there is one, then installs,
        enables and configures the plugin. ``set -euo pipefail``: a config step
        that cannot land fails the trial before the agent runs.
        """

        home = shlex.quote(self._config_home)
        config_dir = shlex.quote(self._config_dir.as_posix())
        omp_env = f"HOME={home} PI_CONFIG_DIR={CONFIG_DIR_NAME}"
        parts: list[str] = [
            "set -euo pipefail",
            install.bun_path_snippet(),
            f"rm -rf {home}",
            f"mkdir -p {config_dir}",
        ]
        if self.options.seed:
            seed = shlex.quote(SEED_DIR.as_posix())
            parts += [f"mkdir -p {seed}", f"cp -a {seed}/. {config_dir}/"]
        plugin = self.options.plugin or {}
        if plugin:
            name = shlex.quote(str(plugin.get("name") or ""))
            # The source was shipped and extracted at install time; the install
            # reads the container path, so no host path reaches the container.
            parts.append(f"{omp_env} omp install {shlex.quote(PLUGIN_DIR.as_posix())}")
            parts.append(f"{omp_env} omp plugin enable {name}")
            for key, value in sorted((plugin.get("settings") or {}).items()):
                parts.append(
                    f"{omp_env} omp plugin config set {name} "
                    f"{shlex.quote(str(key))} {shlex.quote(_setting_value(value))}"
                )
        parts.append("exit 0")
        return "\n".join(parts)

    def _config_extract_command(self) -> str:
        """Extract the shipped config tar into the config dir (strict).

        The tar's members are checkout-relative, so they land exactly where they
        sat in the checkout that carried the config dir.
        """

        return (
            "set -euo pipefail; "
            f"mkdir -p {shlex.quote(self._config_dir.as_posix())} && "
            f"tar -xf {CONFIG_TAR.as_posix()} -C {shlex.quote(self._config_dir.as_posix())}"
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    @override
    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        argv, model = self._run_argv(instruction)
        # The argv is recorded before omp launches (and in an install-only
        # trial), so a trial always shows what it would have run.
        await _upload_json_record(environment, {"argv": argv, "model": model}, RUN_FLAGS_RECORD)
        if self.options.install_only:
            # Prove the install without model spend: nothing launches and no
            # hook command runs.
            return
        await self.exec_as_agent(
            environment,
            command=self._run_command(argv),
            env=dict(self.model_connection.env),
        )

    def _run_command(self, argv: Sequence[str]) -> str:
        """The whole run script: env, hooks, agent, exit status.

        The script is deliberately ``set -uo pipefail`` without ``-e``: the
        agent's status is captured from the pipeline and reported as the exec's
        status, so Harbor's error classifier sees the agent's own failure. The
        hook lines (``hooks.pre_command_lines`` / ``post_command_lines``) carry
        their own status handling.
        """

        session_dir = self.environment_logs_dir / self.options.session_dir_name
        output_path = self.environment_logs_dir / self._OUTPUT_FILENAME
        lines = [
            "set -uo pipefail",
            f"{{ {install.bun_path_snippet()}; }} || true",
            f"mkdir -p {shlex.quote(session_dir.as_posix())} || true",
            # bun and omp were installed under the original home; pin PATH to
            # it before relocating HOME to the isolated config home.
            'ORIG_HOME="$HOME"',
            'export PATH="$ORIG_HOME/.bun/bin:$PATH"',
            f"export HOME={shlex.quote(self._config_home)} PI_CONFIG_DIR={CONFIG_DIR_NAME}",
            # The workspace is the shared cwd for the hooks and the agent.
            f"cd {WORKSPACE_DIR} 2>/dev/null || true",
            *hooks.pre_command_lines(self.options.pre_commands),
            "rc=0",
            f"{' '.join(shlex.quote(part) for part in argv)} "
            f"2>&1 </dev/null | tee {shlex.quote(output_path.as_posix())}",
            "rc=${PIPESTATUS[0]}",
            # Saved before the post-commands run, so nothing they do — not even
            # reusing the agent's variable names — can change this status.
            "harbor_omp_agent_rc=$rc",
            # The post block is one subshell (hooks.post_command_lines), so an
            # exit, an EXIT trap or `set -e` inside it stays inside it.
            *hooks.post_command_lines(self.options.post_commands),
            "exit $harbor_omp_agent_rc",
        ]
        return "\n".join(lines)

    def _effective_run_flags(self) -> list[str]:
        """The flags the run passes: ``run_flags`` when set, else the default."""

        if self.options.run_flags is None:
            return list(MINIMAL_EXTENSIONS_FLAGS)
        return list(self.options.run_flags)

    def _run_argv(self, instruction: str) -> tuple[list[str], str]:
        """The omp argv for this trial and the model it names.

        Raises:
            ValueError: When ``model_name`` is not ``provider/model``.
        """

        if not self.model_name or "/" not in self.model_name:
            raise ValueError("Model name must be in the format provider/model_name")
        session_dir = self.environment_logs_dir / self.options.session_dir_name
        argv = [
            "omp",
            "-p",
            "--auto-approve",
            *self._effective_run_flags(),
            f"--session-dir={session_dir.as_posix()}",
            f"--model={self.model_name}",
        ]
        if self.options.thinking:
            argv.append(f"--thinking={self.options.thinking}")
        argv.append(instruction)
        return argv, self.model_name

    # ------------------------------------------------------------------
    # Post-run metrics
    # ------------------------------------------------------------------
    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        """Sum the session JSONL into the agent context (tokens, cache, cost).

        The per-model breakdown comes from the same pass, so an auxiliary model
        omp reports through ``model_usage`` is visible without an ATIF
        trajectory. A session nobody can read leaves the context empty rather
        than filling it with zeros.

        The trajectory is written last, from the same session and the same
        reader, so its totals and the context's are the same numbers — and a
        conversion the accounting refuses costs the trial no metrics.
        """

        session_dir = self.logs_dir / self.options.session_dir_name
        usage = session.sum_session_usage(session_dir)
        if usage is None:
            self.logger.warning(
                "no readable omp session JSONL under %s (absent, or every file "
                "failed to read); the trial reports no token or cost totals",
                session_dir,
            )
            return
        skipped = (
            usage.skipped_files
            + usage.skipped_lines
            + usage.skipped_values
            + usage.unattributed_records
        )
        if skipped:
            self.logger.warning(
                "omp session JSONL under %s: skipped %d file(s), %d line(s), "
                "%d usage value(s) and %d unattributable usage record(s); the "
                "totals below may be low",
                session_dir,
                usage.skipped_files,
                usage.skipped_lines,
                usage.skipped_values,
                usage.unattributed_records,
            )
        # AgentContext.n_input_tokens includes cached tokens; omp reports them
        # separately, so the total is input + cache read + cache write.
        context.n_input_tokens = usage.total_input_tokens
        context.n_output_tokens = usage.output_tokens
        context.n_cache_tokens = usage.cache_read_tokens
        context.cost_usd = session.reported_cost(usage.cost_usd)
        if usage.models:
            # The same mapping the trajectory's per-model metrics use, so the two
            # cannot report different numbers for the same session.
            context.model_usage = trajectory.model_usage(usage)
        context.metadata = {"omp_steps": usage.steps}
        self._write_trajectory()

    # ------------------------------------------------------------------
    # The ATIF trajectory
    # ------------------------------------------------------------------
    @override
    def convert_trajectory(self, logs_dir: Path) -> Trajectory | None:
        """Build the ATIF trajectory of the omp session under ``logs_dir``.

        One implementation for both producers: Harbor's live stream calls this
        with the temporary logs dir its poll assembled (the session tar under
        ``<logs_dir>/sessions``), and ``_write_trajectory`` calls it with the
        agent's own logs dir after the run. Returns ``None`` when there is no
        session to convert.

        Raises:
            TrajectoryAccountingError: When the session cannot be accounted for
                line by line; see ``harbor_omp.trajectory``.
        """

        return trajectory.convert_trajectory(
            logs_dir,
            session_dir_name=self.options.session_dir_name,
            agent_name=self.name(),
            agent_version=self.version() or "unknown",
            model_name=self.model_name,
        )

    def _write_trajectory(self) -> None:
        """Write ``logs_dir/trajectory.json`` for the session just summed.

        Called only once the context has its numbers, so a refused trajectory
        costs the trial no metrics. Best-effort and loud: a session line that no
        step accounts for, a converter defect or an unwritable path leaves no
        artifact and an error line naming why — a trajectory that is missing or
        wrong must never look like one that is complete.
        """

        path = self.logs_dir / trajectory.TRAJECTORY_FILENAME
        try:
            built = self.convert_trajectory(self.logs_dir)
            if built is None:
                self.logger.warning(
                    "no non-blank omp session line under %s to convert; no ATIF "
                    "trajectory written to %s",
                    self.logs_dir / self.options.session_dir_name,
                    path,
                )
                return
            errors = trajectory.write_trajectory(path, built)
        except (trajectory.TrajectoryAccountingError, ValidationError, OSError) as exc:
            self.logger.error("harbor-omp: no ATIF trajectory at %s: %s", path, exc)
            return
        if errors:
            self.logger.error(
                "harbor-omp: no ATIF trajectory at %s; Harbor's validator rejected it: %s",
                path,
                "; ".join(errors),
            )
            return
        self.logger.debug("wrote the ATIF trajectory to %s", path)

    @property
    @override
    def remote_session_logs_dir(self) -> PurePosixPath | None:
        """The session JSONL directory (under Harbor's mounted log dir)."""

        return self.environment_logs_dir / self.options.session_dir_name
