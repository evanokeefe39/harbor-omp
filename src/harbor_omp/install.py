"""Installing omp in the trial container, and probing its version.

omp is a bun tool: the install path is bun's global installer, not npm. bun's
own installer needs ``unzip`` present, hence the system dependencies; without
it bun exits 1 with ``error: unzip is required to install bun`` and the trial
never reaches the agent.

The install is strict (``set -euo pipefail``): a failed install fails the trial
at setup, before any model spend. ``--ignore-scripts`` keeps package lifecycle
scripts out of the container.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from pathlib import PurePosixPath

#: Harbor's agent log dir inside the container, mounted back to the host.
AGENT_LOG_DIR = PurePosixPath("/logs/agent")

#: Where the adapter's provenance records land inside the container.
RESOLVED_DIR = AGENT_LOG_DIR / "resolved"

#: System packages the install and the git-based shipping steps need.
SYSTEM_DEPENDENCIES: tuple[str, ...] = ("curl", "git", "unzip")


def bun_path_snippet() -> str:
    """Install bun when it is missing, and put it on PATH for this command.

    Succeeds when bun is already present, so it is safe to prepend to any
    command that needs bun or omp.
    """

    return (
        "if ! command -v bun >/dev/null 2>&1; then "
        "curl -fsSL https://bun.sh/install | bash; fi && "
        'export PATH="$HOME/.bun/bin:$PATH"'
    )


def install_command(spec: str, *, directories: Sequence[PurePosixPath] = ()) -> str:
    """The agent-user command that installs ``spec`` and prepares log dirs.

    Post: bun is on PATH, ``spec`` is installed globally with scripts
    disabled, ``omp --version`` printed the installed version, and every
    directory in ``directories`` exists.

    Raises:
        ValueError: If ``spec`` is blank (see ``options.package_spec``).
    """

    if not spec.strip():
        raise ValueError(
            "the install command needs a package spec "
            "(for example '@oh-my-pi/pi-coding-agent@18.6.0')"
        )
    layout = " ".join(shlex.quote(directory.as_posix()) for directory in directories)
    command = (
        "set -euo pipefail; "
        f"{bun_path_snippet()} && "
        f"bun install -g --ignore-scripts {shlex.quote(spec)} && "
        "omp --version"
    )
    if layout:
        command += f" && mkdir -p {layout}"
    return command


def version_command() -> str:
    """The version probe: the installed omp version, or a readable marker."""

    return f"{bun_path_snippet()} && omp --version 2>/dev/null || echo 'not installed'"


def parse_version(stdout: str) -> str:
    """The last non-empty line of the probe output (omp prints one line)."""

    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    return lines[-1] if lines else ""
