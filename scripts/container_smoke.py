"""Exercise the container-side recipes in a real Linux container.

The unit tests assert the commands the adapter hands to an environment; this
script runs those same commands on a real filesystem, with the real bun and the
real omp install, and checks the results it can only get there:

* the install command leaves a working ``omp`` on PATH;
* the config home step lands a seed at ``<config_home>/.omp/<relpath>``;
* the real CLI runs under the isolated ``HOME``/``PI_CONFIG_DIR``;
* the run script's pre-command export reaches the agent, a failing pre-command
  aborts before it, and the agent's own status is what the script reports —
  even when a post-command exits.

Requires Docker and network access (bun's installer and the npm registry). It is
**not** part of CI, and it never calls a model: the agent itself is stubbed.

Usage::

    uv run python scripts/container_smoke.py [--image ubuntu:24.04] [--timeout 1500]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

from harbor_omp import OmpAgent
from harbor_omp.install import install_command

MODEL = "openrouter/deepseek/deepseek-v4-flash"
SEED = {"omp.json": '{"model": "smoke"}\n', "agent/config.yml": "task: {}\n"}

#: The two agent stubs: the run script sources one of these before the adapter's
#: script, so no model is called and the argv it received is visible.
STUB_OK = (
    'omp() { echo "AGENT-STUB probe=${HOOK_PROBE-unset} argv=$*";\n'
    '  return "${FAKE_OMP_RC:-0}"; }\n'
    "bun() { :; }\n"
)
STUB_FAIL = 'omp() { echo "AGENT-STUB-RAN"; }\nbun() { :; }\n'

DRIVER = r"""#!/usr/bin/env bash
echo "== system dependencies (what ensure_system_dependencies does) =="
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq curl git unzip ca-certificates >/dev/null 2>&1
for b in curl git unzip; do command -v "$b" >/dev/null || echo "MISSING $b"; done
echo "== install =="
bash /work/install.sh; echo "install rc=$?"
export PATH="$HOME/.bun/bin:$PATH"
command -v omp; omp --version
echo "== stage the seed the way the adapter's upload would =="
mkdir -p /tmp/harbor-omp-seed/agent
printf '{"model": "smoke"}\n' > /tmp/harbor-omp-seed/omp.json
printf 'task: {}\n' > /tmp/harbor-omp-seed/agent/config.yml
echo "== config home step =="
bash /work/home.sh; echo "home rc=$?"
find /tmp/omp-home | sort
echo "== the real CLI under the isolated home =="
HOME=/tmp/omp-home PI_CONFIG_DIR=.omp omp --version
echo "== run script, agent stubbed =="
bash -c 'source /work/stub_ok.sh; source /work/run.sh'; echo "run rc=$?"
echo "== failing pre-command must abort before the agent =="
bash -c 'source /work/stub_fail.sh; source /work/run_failpre.sh'; echo "run rc=$?"
echo "== agent rc 7 must propagate, post-command still runs =="
FAKE_OMP_RC=7 bash -c 'source /work/stub_ok.sh; source /work/run.sh'; echo "run rc=$?"
echo "== a post-command that exits must not replace that status =="
FAKE_OMP_RC=7 bash -c 'source /work/stub_ok.sh; source /work/run_exit.sh'
echo "post-exit rc=$?"
echo "== captured agent output =="; cat /logs/agent/omp.txt
"""

#: Evidence the driver must produce. A missing line is a failed check — silence
#: must never read as success.
EXPECTED = (
    "install rc=0",
    "omp/18.6.0",
    "/tmp/omp-home/.omp/omp.json",
    "/tmp/omp-home/.omp/agent/config.yml",
    "probe=from-pre-command",
    "pre-command failed (rc=1)",
    "aborting before the agent runs",
    "run rc=1",
    "run rc=7",
    "post-exit rc=7",
    "POST-RAN",
)


def _agent(**options: object) -> OmpAgent:
    defaults: dict[str, object] = {
        "logs_dir": Path("logs"),
        "model_name": MODEL,
        "environment_logs_dir": PurePosixPath("/logs/agent"),
    }
    defaults.update(options)
    return OmpAgent(**defaults)


def _write_scripts(work: Path) -> None:
    """Write each adapter-generated command as the standalone script it is."""

    seeded = _agent(
        seed=SEED,
        pre_commands=["export HOOK_PROBE=from-pre-command"],
        post_commands=["echo POST-RAN"],
    )
    failing = _agent(seed={"omp.json": "{}\n"}, pre_commands=["false"])
    post_exit = _agent(post_commands=["echo POST-RAN; exit 0"])
    argv, _ = seeded._run_argv("do the task")
    fail_argv, _ = failing._run_argv("do the task")
    post_exit_argv, _ = post_exit._run_argv("do the task")
    scripts = {
        "install.sh": install_command(
            seeded.options.version,
            directories=(
                PurePosixPath("/logs/agent/omp-sessions"),
                PurePosixPath("/logs/agent/resolved"),
            ),
        ),
        "home.sh": seeded._config_home_command(),
        "run.sh": seeded._run_command(argv),
        "run_failpre.sh": failing._run_command(fail_argv),
        "run_exit.sh": post_exit._run_command(post_exit_argv),
        "stub_ok.sh": STUB_OK,
        "stub_fail.sh": STUB_FAIL,
        "driver.sh": DRIVER,
    }
    for name, body in scripts.items():
        (work / name).write_text(body + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="container smoke for harbor-omp")
    parser.add_argument("--image", default="ubuntu:24.04")
    parser.add_argument("--timeout", type=int, default=1500)
    parser.add_argument(
        "--keep", action="store_true", help="keep the generated scripts for inspection"
    )
    args = parser.parse_args()

    if shutil.which("docker") is None:
        print("docker is not available: this check needs a container runtime")
        return 2

    work = Path(tempfile.mkdtemp(prefix="harbor-omp-smoke-"))
    try:
        _write_scripts(work)
        print(f"scripts in {work}")
        env = dict(os.environ)
        # Git Bash must not rewrite the container path inside -v on Windows.
        env.setdefault("MSYS_NO_PATHCONV", "1")
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{work.as_posix()}:/work",
                args.image,
                "bash",
                "/work/driver.sh",
            ],
            capture_output=True,
            text=True,
            timeout=args.timeout,
            env=env,
            check=False,
        )
        output = result.stdout + result.stderr
        print(output)
        if result.returncode != 0:
            print(f"the container run failed (exit {result.returncode})")
            return 1
        missing = [line for line in EXPECTED if line not in output]
        if missing:
            print("missing expected evidence:")
            for line in missing:
                print(f"  {line!r}")
            return 1
        print("container smoke: all expected evidence present")
        return 0
    finally:
        if args.keep:
            print(f"kept {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
