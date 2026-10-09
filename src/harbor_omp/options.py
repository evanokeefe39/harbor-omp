"""The adapter's option surface (Harbor's ``AgentConfig.kwargs``).

Everything the adapter needs to know arrives here as data. Nothing in this
package reads a benchmark, a profile, or a harness module: a caller that wants
a pinned omp, shipped config content, a plugin, or its own commands says so
with these fields.

The option names are the contract — Harbor accepts them as
``--agent-kwarg name=value``, one per field.
"""

from __future__ import annotations

from typing import Any

from harbor.agents.options import InstalledAgentOptions
from pydantic import AliasChoices, Field, field_validator, model_validator

#: The npm package that ships the omp CLI.
OMP_PACKAGE = "@oh-my-pi/pi-coding-agent"

#: The omp dist the install pins when ``version`` is left alone.
PINNED_OMP_VERSION = f"{OMP_PACKAGE}@18.6.0"

#: The run flags a trial with no ``run_flags`` uses: every optional extension
#: off, which is what keeps a trial's tools the ones the caller pinned.
#: ``--no-extensions`` also gates omp plugins, so this default is refused
#: alongside ``plugin`` (see ``OmpOptions``); ``[]`` runs omp with its own
#: defaults.
MINIMAL_EXTENSIONS_FLAGS: tuple[str, ...] = (
    "--no-extensions",
    "--no-skills",
    "--no-rules",
    "--no-lsp",
)


def package_spec(version: str) -> str:
    """Normalise ``version`` into the npm spec the install command installs.

    ``@oh-my-pi/pi-coding-agent@18.6.0`` (the default) and any other scoped or
    namespaced spec pass through verbatim, so a caller may pin a fork; a bare
    version such as ``18.6.1`` becomes ``@oh-my-pi/pi-coding-agent@18.6.1``, so
    ``--agent-kwarg version=18.6.1`` reads like what it does.

    Raises:
        ValueError: If ``version`` is blank — an install that cannot name its
            package would silently install whatever the registry resolves.
    """

    value = version.strip()
    if not value:
        raise ValueError(
            "the version option is blank; the install must name the package it "
            "installs (for example '@oh-my-pi/pi-coding-agent@18.6.0')"
        )
    if value.startswith("@") or "/" in value:
        return value
    return f"{OMP_PACKAGE}@{value}"


class OmpOptions(InstalledAgentOptions):
    """Everything the adapter is told, and nothing it assumes."""

    @field_validator("version", mode="before")
    @classmethod
    def _pinned_unless_given(cls, value: object) -> object:
        """None means "not specified", which is the pin.

        ``BaseInstalledAgent.__init__`` always forwards ``version=None`` into
        the options model, so without this every unset version would arrive as
        None and the install could not name its package.
        """

        return PINNED_OMP_VERSION if value is None else value

    @field_validator("session_dir_name")
    @classmethod
    def _one_path_segment(cls, value: str) -> str:
        """The name is spliced into container paths and shell commands, so it
        must be one relative path segment.

        Raises:
            ValueError: When the value is blank, carries whitespace, or is not a
                single path segment — a name with a separator would silently
                write outside the environment log dir, and one with a space
                would split into two arguments.
        """

        if not value or any(character.isspace() for character in value):
            raise ValueError(
                f"session_dir_name={value!r} must be one path segment with no "
                "whitespace (for example 'omp-sessions'); it is spliced into "
                "container paths and shell commands"
            )
        if value in (".", "..") or "/" in value or "\\" in value:
            raise ValueError(
                f"session_dir_name={value!r} must be one path segment with no "
                "separators (for example 'omp-sessions'); it is spliced into "
                "container paths and shell commands"
            )
        return value

    @model_validator(mode="after")
    def _a_plugin_needs_flags_that_load_it(self) -> OmpOptions:
        """Refuse a plugin the default flags would disable.

        ``--no-extensions`` also gates plugin discovery, so ``plugin`` with the
        default recipe would install a plugin that never loads — with no error
        from omp and no sign in the trial.

        Raises:
            ValueError: When ``plugin`` is set and ``run_flags`` is unset.
        """

        if self.plugin is not None and self.run_flags is None:
            raise ValueError(
                "plugin is set but run_flags is unset; the default flags "
                "include --no-extensions, which also disables plugin loading, "
                "so the plugin would install and never load. Pass run_flags "
                "explicitly (run_flags=[] runs omp with its own defaults)"
            )
        return self

    version: str = Field(
        default=PINNED_OMP_VERSION,
        description=(
            "The npm package spec to install, honoured by the install command. "
            "A bare version (18.6.1) is read as a version of @oh-my-pi/"
            "pi-coding-agent."
        ),
    )
    thinking: str | None = Field(
        default=None,
        validation_alias=AliasChoices("thinking", "reasoning_effort"),
        description="Thinking level passed to omp as --thinking=<value>.",
    )
    run_flags: list[str] | None = Field(
        default=None,
        description=(
            "The omp flags the run passes, verbatim and in order. None uses the "
            "minimal-extension default (--no-extensions --no-skills --no-rules "
            "--no-lsp); [] runs omp with its own defaults. A trial that installs "
            "a plugin must pass its flags explicitly, because the minimal "
            "default also disables plugin loading. The exact argv is recorded "
            "in run-flags.json before omp launches."
        ),
    )
    install_only: bool = Field(
        default=False,
        description=(
            "Prove the install without model spend: run() records the exact argv "
            "and returns without invoking omp, and no hook command runs."
        ),
    )
    config_source: str | None = Field(
        default=None,
        description=(
            "A HOST path to a git checkout whose committed HEAD carries config "
            "content to ship (skills, rules, agents, hooks). The shipped paths "
            "must have no uncommitted changes to tracked files; the archive is "
            "restricted to config_paths; the tar is extracted into the isolated "
            "config dir after the home is reset. A source that cannot be pinned "
            "aborts the trial before any upload and before any model spend."
        ),
    )
    config_paths: list[str] | None = Field(
        default=None,
        description=(
            "Checkout-relative paths to ship from config_source, verbatim as "
            "git archive pathspecs, so 'agent/skills/duckdb/' lands at "
            "<config_home>/.omp/agent/skills/duckdb/. None or empty with "
            "config_source set is refused: a config ship that names nothing "
            "would silently ship nothing."
        ),
    )
    plugin: dict[str, Any] | None = Field(
        default=None,
        description=(
            'A plugin to install: {"name", "src" (a HOST path to a git checkout '
            'of the plugin), "settings" (optional {key: value} passed to '
            '"omp plugin config set")}. The committed HEAD is archived, '
            "uploaded, extracted in the container as the agent user, installed "
            "with 'omp install', enabled, and configured during the config-home "
            "step. A dirty or missing source aborts before any upload and "
            "before any model spend."
        ),
    )
    seed: dict[str, str] | None = Field(
        default=None,
        description=(
            "Config-dir-relative path -> file content, written into the isolated "
            "config home (<config_home>/.omp/<path>) before the agent runs. "
            "Plain data: the adapter neither reads nor renders it. Absolute "
            "paths and '..' segments are refused."
        ),
    )
    config_home: str = Field(
        default="/tmp/omp-home",
        description=(
            "The HOME the agent runs under, and the root of the isolated config "
            "dir (<config_home>/.omp, with PI_CONFIG_DIR=.omp). The adapter "
            "resets it on every install, so point it at a path this trial owns."
        ),
    )
    session_dir_name: str = Field(
        default="omp-sessions",
        description=(
            "Session directory name under the environment log dir; omp is "
            "launched with --session-dir pointing at it, and the post-run "
            "metrics are read back from there."
        ),
    )
    extra_files: list[tuple[str, str]] | None = Field(
        default=None,
        description=(
            "Extension point: (host path, container path) pairs uploaded during "
            "install as the agent user, after omp is installed and before any "
            "command hook runs. File modes are not preserved — chmod in a "
            "pre-command when the file must be executable. See hooks.py."
        ),
    )
    pre_commands: list[str] | None = Field(
        default=None,
        description=(
            "Extension point: shell commands run as the agent user in the same "
            "shell that launches omp, in order, before the agent starts. An "
            "export here reaches the agent process; a non-zero exit aborts the "
            "run before the agent starts (the pre-spend gate). See hooks.py."
        ),
    )
    post_commands: list[str] | None = Field(
        default=None,
        description=(
            "Extension point: shell commands run as the agent user after omp "
            "exits and before the run exits. Best-effort: a failure is reported "
            "on stderr and can never change the agent's exit code. See hooks.py."
        ),
    )
