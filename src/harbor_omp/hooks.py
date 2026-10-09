"""The adapter's extension points: extra files, pre-commands, post-commands.

The adapter knows how to install omp, keep it away from ambient config, run it,
and read its session metrics. It knows nothing about a benchmark, a profile, an
evidence collector, or a scan list. Everything a consumer adds arrives through
the three hooks below — the fields live on ``OmpOptions`` (``extra_files``,
``pre_commands``, ``post_commands``) and this module owns their semantics.

``extra_files`` — uploads
    ``(host path, container path)`` pairs, uploaded during ``install()`` as the
    agent user, after omp is installed and before any command hook runs. A host
    path that is not a readable file raises: shipping nothing silently is worse
    than failing the setup. File modes are not preserved, so a pre-command that
    needs an executable does its own ``chmod``.

``pre_commands`` — the pre-spend gate
    Shell commands run as the agent user, in the same shell that launches omp,
    in order, after the isolated config home is ready. Two consequences, both
    deliberate:

    * An ``export`` in a pre-command reaches the agent process. This is the way
      to give the agent extra environment variables; there is no separate env
      hook.
    * A pre-command that exits non-zero aborts the run before the agent starts,
      so a trial never spends model tokens on an environment that failed its
      own checks. A harness that wants a best-effort pre-command writes
      ``... || true`` itself.

``post_commands`` — best-effort collection
    Shell commands run as the agent user after omp exits and before the run
    exits. A post-command can never change the agent's exit code: the adapter
    keeps the agent's status, reports a non-zero post-command on stderr, and
    exits with the agent's status. Evidence collection must not turn a passing
    trial red, and must not hide a failing one behind its own failure.

The commands are the caller's shell text. The adapter runs them in one script
with the agent, so the caller's lines share its working directory (``/app``)
and its isolated ``HOME`` / ``PI_CONFIG_DIR``. The adapter's own variables are
``rc``, ``harbor_omp_agent_rc`` and ``harbor_omp_hook_rc`` — a hook that
reuses those names changes its own result, not the agent's exit code.
"""

from __future__ import annotations

from collections.abc import Sequence

#: The variable the pre/post hooks report their own status in.
_HOOK_RC = "harbor_omp_hook_rc"


def pre_command_lines(commands: Sequence[str] | None) -> list[str]:
    """Render pre-commands as script lines that abort on the first failure.

    Each command keeps its own exit status: the script prints the status and
    exits with it, so a failed gate is reported with the status that failed.
    """

    lines: list[str] = []
    for command in commands or ():
        lines += [
            command,
            f"{_HOOK_RC}=$?",
            f'if [ "${{{_HOOK_RC}}}" -ne 0 ]; then',
            (
                f'  echo "harbor-omp: pre-command failed (rc=${_HOOK_RC}); '
                'aborting before the agent runs" >&2'
            ),
            f'  exit "${{{_HOOK_RC}}}"',
            "fi",
        ]
    return lines


def post_command_lines(commands: Sequence[str] | None) -> list[str]:
    """Render post-commands as script lines that never change the exit code.

    The script has already saved the agent's status in ``harbor_omp_agent_rc``
    and exits with that value, so a failing post-command is loud (stderr) but
    cannot turn a red trial green or the reverse.
    """

    lines: list[str] = []
    for command in commands or ():
        lines += [
            command,
            f"{_HOOK_RC}=$?",
            f'if [ "${_HOOK_RC}" -ne 0 ]; then',
            (
                f'  echo "harbor-omp: post-command failed (rc=${_HOOK_RC}); '
                'the agent exit code is unchanged" >&2'
            ),
            "fi",
        ]
    return lines
