# Architecture

## Modules

| Module | Responsibility | Depends on |
|---|---|---|
| `harbor_omp/omp_agent.py` | The Harbor adapter: `OmpAgent`, shipping, config-home steps, the run script, post-run metrics. | Harbor, pydantic, the rest of the package |
| `harbor_omp/options.py` | The option model and the npm-spec normalisation. | pydantic, Harbor's options base |
| `harbor_omp/install.py` | bun and omp installation, the version probe, container paths. | stdlib |
| `harbor_omp/session.py` | The session JSONL reader: usage, cost, steps. | **stdlib only** |
| `harbor_omp/hooks.py` | The documented extension points and the shell lines they compile to. | stdlib |

Two boundaries are deliberate:

- `session.py` has no third-party import, so a harness that runs omp without
  Harbor can still read a session (enforced by a test).
- Nothing in the package imports a benchmark, a profile, or an eval harness. The
  only names it knows from the outside world are the options a caller passes
  (enforced by a test and a source scan).

## Lifecycle

```
Harbor                 OmpAgent                          container
------                 --------                          ---------
setup() ─────────────▶ install()
                       ├─ archive plugin checkout HEAD ─▶ /tmp/harbor-omp-plugin.tar
                       │                                  /tmp/harbor-omp-plugin/       (agent user)
                       ├─ archive config checkout HEAD ─▶ /tmp/harbor-omp-config.tar
                       │                                  /logs/agent/resolved/config-source.json
                       ├─ ensure_system_dependencies
                       ├─ bun + bun install -g omp ─────▶ omp --version
                       ├─ extra_files uploads ──────────▶ caller's targets
                       └─ reset config home ────────────▶ $HOME/.omp  (seed, plugin install/enable/config)
                                          (config tar extracted into $HOME/.omp after the reset)
       version probe ◀── get_version_command() ──────────▶ omp --version
run()  ─────────────▶ run()
                       ├─ run-flags.json record ────────▶ /logs/agent/resolved/run-flags.json
                       ├─ install_only? ────────────────▶ (stop; no agent, no hooks)
                       └─ run script ───────────────────▶ pre-commands
                                                          omp … | tee /logs/agent/omp.txt
                                                          post-commands
   sync logs ◀──────── logs_dir/<session_dir_name>/ ◀───── /logs/agent/omp-sessions/
       metrics ◀────── populate_context_post_run()  ─────▶ (read from logs_dir)
```

The run script is one shell, in this order:

```bash
set -uo pipefail
{ bun…; } || true                      # the agent may need bun's global bin on PATH
mkdir -p <logs>/<session_dir_name> || true
ORIG_HOME="$HOME"; export PATH="$ORIG_HOME/.bun/bin:$PATH"
export HOME=<config_home> PI_CONFIG_DIR=.omp
cd /app 2>/dev/null || true            # hooks and the agent share one cwd
<pre-commands>                         # exports reach the agent; a failure aborts here
rc=0
<omp argv …> 2>&1 </dev/null | tee <logs>/omp.txt
rc=${PIPESTATUS[0]}
harbor_omp_agent_rc=$rc                # saved before the post-commands can touch anything
(                                      # the post block is one subshell: `exit`,
  <post-commands>                      # an EXIT trap or `set -e` inside it ends the
)                                      # subshell and nothing else
harbor_omp_hook_rc=$?                  # the block's own status, reported by the parent
if [ "$harbor_omp_hook_rc" -ne 0 ]; then
  echo "harbor-omp: post-command failed (rc=…); the agent exit code is unchanged" >&2
fi
exit $harbor_omp_agent_rc
```

Why `set -uo pipefail` and not `-e`: the agent's status is captured from the
pipeline and reported as the exec's status, so Harbor's error classifier sees
omp's own failure instead of the last command in a chain — and the same reason
puts the post block in a subshell, so a post-command cannot end the script
before its status is recorded or replace it at exit.

## The seam

Everything a consumer adds arrives as option data:

- **files** — `extra_files`, uploaded during install as the agent user;
- **commands** — `pre_commands` (a gate: non-zero aborts before the agent, and
  an `export` here reaches the agent process) and `post_commands` (collection:
  one contained subshell, best-effort by construction);
- **config** — `seed` (config-dir-relative content) and `config_source` +
  `config_paths` (a host checkout shipped by committed HEAD).

The alternative — importing the consumer's modules — is what this package was
extracted to avoid: it makes neither side reusable and neither side testable.

## The ATIF seam (not implemented)

Harbor's `atif` capability is declared false and `convert_trajectory` is **not**
overridden, so no `logs_dir/trajectory.json` is written. When it is added, the
shape is:

1. `harbor_omp/trajectory.py` builds a `harbor.models.trajectories.Trajectory`
   from the session JSONL, read through `session.iter_session_events` (the
   streaming reader already exists for this);
2. `OmpAgent.convert_trajectory(logs_dir)` returns it, which serves both the
   post-run path and, once `environment.stream` is used, the live path
   (`remote_session_logs_dir` already points at the right directory);
3. `capabilities.atif` flips to true and the README known-gaps row moves;
4. per-model `model_usage` is **already** populated from the session
   (`session.sum_session_usage` returns the per-model totals and the adapter
   maps them onto `AgentContext.model_usage`), so the trajectory does not have
   to supply it.

Until then, tokens, cache and cost come from the session JSONL directly — the
same numbers, without a trajectory artifact.
