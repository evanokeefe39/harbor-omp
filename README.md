# harbor-omp

A [Harbor](https://docs.harborframework.com) agent for
**omp** — the coding-agent CLI shipped by the npm package
`@oh-my-pi/pi-coding-agent`. It installs a pinned omp with bun inside the trial container, runs it
under an isolated config home, records the argv it ran, and turns the omp
session log into the token, cache and cost numbers Harbor reports — plus the
ATIF trajectory Harbor's viewer, `atif2otel` and the observability plugins read.

## Why this exists

Harbor ships agents for `claude-code`, `codex`, `pi`, `opencode` and others,
but none for omp — the agent CLI this package exists to run. This package was
extracted from a private evaluation harness so the agent could be reused
instead of vendored: it depends on Harbor's public API only, and on nothing from
the harness it came from (see `docs/architecture.md`).

The result is small on purpose: `OmpAgent` plus a stdlib-only session reader.
Everything benchmark-shaped — performance profiles, evidence collectors,
contamination scans, toolchain contracts — is *input* to this package, never an
import (see [Extension points](#extension-points)).

## Install

```bash
uv add harbor-omp        # or: uv pip install harbor-omp
```

`harbor run` resolves agents by name or by import path, and there is no agent
entry point group, so the import path is the supported invocation — `--agent`
takes it:

```bash
harbor run --path <dataset> --include-task-name <task> \
  --agent harbor_omp:OmpAgent \
  --model openrouter/deepseek/deepseek-v4-flash
```

`--agent-import-path` is the same flag under its deprecated (pre-0.24) name and
prints a deprecation warning. `--task` is read only when no `--path` is given,
so selecting one task out of a local dataset needs `--include-task-name` —
`--task` beside `--path` resolves the whole dataset without saying so.

**Harbor's interpreter must be able to import this package.** If Harbor is
installed as a tool rather than a project dependency, inject it:

```bash
uv tool install harbor --with harbor-omp
```

### Configuration

Options are Harbor agent kwargs (`--agent-kwarg name=value`):

```bash
harbor run --path <dataset> --include-task-name <task> \
  --agent harbor_omp:OmpAgent \
  --model openrouter/deepseek/deepseek-v4-flash \
  --agent-kwarg version=@oh-my-pi/pi-coding-agent@18.6.0 \
  --agent-kwarg thinking=high \
  --agent-kwarg run_flags='["--no-extensions"]' \
  --agent-kwarg config_home=/tmp/trial-home
```

| Option | Default | What it does |
|---|---|---|
| `version` | `@oh-my-pi/pi-coding-agent@18.6.0` | The npm spec the install installs (honoured, not advisory). A bare `18.6.1` is read as a version of the omp package. |
| `thinking` | unset | Passed to omp as `--thinking=<value>`. Also accepts `reasoning_effort` as a name. |
| `run_flags` | minimal extensions | The omp flags the run passes, verbatim. Unset means `--no-extensions --no-skills --no-rules --no-lsp`; `[]` runs omp with its own defaults. A trial that sets `plugin` must pass its flags explicitly, because `--no-extensions` also gates plugin loading — that combination is refused rather than installed silently. |
| `install_only` | `false` | Record the argv, run no agent and no hook command, spend nothing. The zero-spend install gate. |
| `config_source` + `config_paths` | unset | A host git checkout whose committed HEAD ships into the config dir: paths are checkout-relative archive pathspecs. Both must be given; the shipped paths must have no uncommitted changes to tracked files, or the trial aborts before any upload (a dirty file elsewhere in the checkout does not abort — it does not ship). |
| `plugin` | unset | `{"name", "src", "settings"}`: a host git checkout of an omp plugin, installed in-container with `omp install`, enabled, and configured via `omp plugin config set`. Needs explicit `run_flags`. |
| `seed` | unset | Config-dir-relative path → file content, written into the isolated config dir before the agent runs. Plain data; the agent neither reads nor renders it. |
| `config_home` | `/tmp/omp-home` | The HOME the agent runs under. `<config_home>/.omp` is the config dir (`PI_CONFIG_DIR=.omp`). Reset on every install. |
| `session_dir_name` | `omp-sessions` | Session directory under the environment log dir; `--session-dir` points at it and the post-run metrics are read from it. |
| `extra_files`, `pre_commands`, `post_commands` | unset | The extension points — see below. |

## What the agent does

1. **Ships the pins.** A plugin source and a config checkout are verified clean
   and archived from their committed HEAD *before* anything is uploaded: a pin
   that cannot land fails the trial before any model spend. The archive never
   contains uncommitted work, so what ran is what was reviewed.
2. **Installs omp.** `curl`/`git`/`unzip` via the distro, then bun, then
   `bun install -g --ignore-scripts <version>`, then `omp --version`. Strict:
   a failed install fails the trial at setup.
3. **Builds the isolated config home.** `HOME=<config_home>` with
   `PI_CONFIG_DIR=.omp` is reset on every install, seeded from `seed`, filled
   from the shipped config checkout, and configured with the plugin. The agent
   never reads the operator's own `~/.omp`.
4. **Runs the agent.** `omp -p --auto-approve <run_flags>
   --session-dir=<logs>/<session_dir_name> --model=<provider/model>
   [--thinking=<value>] <instruction>`, with output captured to
   `<logs>/omp.txt` and the process status reported unchanged to Harbor. The
   exact argv is recorded in `/logs/agent/resolved/run-flags.json` before omp
   launches, in install-only trials too. **After omp exits 0, the session must
   contain at least one tool call**, or the run is reported as a failed agent
   run (see the limits below).
5. **Reports the metrics.** After the run, the session JSONL is summed into
    `AgentContext`: input tokens (including cache), cache tokens, output tokens,
    the cost omp itself reported, the step count, and the per-model breakdown
    (`AgentContext.model_usage`) from the same pass. omp's `model_usage` events
    — an auxiliary model, for example the one behind a `find` tool — are summed
    too: they are additional to the assistant messages, and ignoring them
    under-reports a trial. Provider-reported cost is preferred; nothing is
    estimated.
6. **Writes the trajectory.** The same session is converted into an ATIF
    trajectory at `<logs>/trajectory.json`: one step per session line, in order,
    each carrying its line's decoded payload under `extra.omp_event`, with
    `final_metrics` equal to the context's numbers. `message` events become
    conversation steps and every other event (session lifecycle, config
    changes, tool dispatches, an auxiliary model's usage) becomes a `system`
    step — nothing is dropped, and a line that would be dropped fails the
    conversion loudly instead. A streaming job keeps the same file current
    while the run is going (see the capabilities table).

## Extension points

Everything a consumer adds arrives as data through three options, documented in
`src/harbor_omp/hooks.py`:

| Option | Semantics |
|---|---|
| `extra_files` | `(host path, container path)` pairs uploaded during install, as the agent user, after omp is installed. A missing host file fails the setup. |
| `pre_commands` | Shell commands run as the agent user in the same shell that launches omp. An `export` reaches the agent process; a non-zero exit aborts before the agent starts, so no tokens are spent on a failed check. |
| `post_commands` | Shell commands run after omp exits, all inside one subshell. Best-effort by construction: a failure is reported on stderr and can never change the agent's exit code — an `exit`, an `EXIT` trap or a `set -e` inside the block ends the block and nothing else. |

That is how a harness attaches its own evidence collector, gh shim, scan lists
or toolchain probes without this package importing any of them.

## Capabilities and known gaps

`OmpAgent.capabilities` declares only what is implemented, so Harbor refuses a
job that asks for more instead of silently under-delivering:

| Capability | Declared | Notes |
|---|---|---|
| ATIF trajectory (`atif`) | **yes** | `logs_dir/trajectory.json` is written after every run from the same session the metrics come from, and is validated by Harbor's own `trajectory_validator` before it lands. One step per session line with the line's payload verbatim under `extra.omp_event`; a torn line refuses the whole conversion rather than producing a shorter artifact. `final_metrics` carry the context's totals, including the auxiliary model, whose per-model numbers are in `final_metrics.extra.models` (a `system` step may not carry ATIF `metrics`). |
| resume | **yes** | `_run_argv` appends `--continue` when `self._resume` is true (set by the base class's `resume()`). |
| load native | **yes** | `_run_argv` appends `--resume <stem>` when `self._load` is true and a session was seeded; `_upload_load_trajectory` places the file in the container session dir; `_validate_native_load_trajectory` rejects anything that is not omp session JSONL. |
| load ATIF | **no** | ATIF-to-native conversion is lossy (tool-result pairing, thinking blocks), so a loaded session would be a fabricated history. |
| handoff | **yes** | `handoff(cls, trial_dir, cwd)` copies the trial's single session into the local session dir (`~/.omp/sessions/`, respecting `PI_CONFIG_DIR`) and returns `["omp", "--resume", <stem>]`. Requires `omp` on PATH and exactly one session. |
| native config (`config=`) | **no** | Consumer config already travels through `seed` / `config_source`; Harbor's `config=` would be a second channel that still only writes files. |
| skills | **yes** | When `skills_dir` is set, `_config_home_command` copies its immediate children into `<config_dir>/agent/skills/` so omp discovers `<skill>/SKILL.md`, and a missing, unreadable or **empty** `skills_dir` fails the step loudly (strict — no `\|\| true` swallow; a skills_dir is only set when skills were meant to arrive). A consumer `run_flag` that disables discovery (`--no-skills`) still wins for that run — it is explicit config. |
| MCP servers | **yes** | When `mcp_servers` is non-empty, `_config_home_command` writes `<config_dir>/agent/mcp.json` (stdio → `type`/`command`/`args`; `streamable-http` → `http` + `url`; SSE → `sse` + `url`). |
| live streaming | **partly** | The converters are the streaming half: a `--stream` job (needs `environment.stream: true` in the job config) makes Harbor tar the session JSONL into a temp `<logs_dir>/sessions/` every ~2 s and call `convert_trajectory`, which now builds a trajectory from exactly that layout, so the trial's `agent/trajectory.json` is populated while the run is still going and rewritten complete after it. Not declared as a capability because Harbor has no streaming flag to declare: `environment.stream` is the switch, and `remote_session_logs_dir` already points at the mounted session dir. **What it still does not produce:** the trajectory is the only thing kept current — `AgentContext` (tokens, cache, cost) is still filled after the run, so a live viewer shows steps without metrics; the streamed file is written by Harbor's own writer, so it bypasses the validator gate the post-run write applies; and a poll that catches a half-written session line refuses *that poll* rather than publishing a partial trajectory, so the file is refreshed on the next one. |

Other deliberate limits:

- **The error type Harbor reports is prose-derived.** omp runs in text mode
  (`-p`), so the output Harbor's classifier scans on a failed run is the
  agent's own prose, matched against Harbor's 34 error regexes.
  `filter_jsonl_events` cannot narrow that to harness-emitted events the way a
  JSONL-speaking agent does, because there is no JSONL stream at exec time.
  A failed trial is still classified (and its status is omp's own), but treat
  the error type as a hint rather than as a structured field.
- **No per-exec timeout.** A hung omp runs to Harbor's task timeout rather than
  a per-execution bound.
- **Mid-run metrics are a platform limit.** Harbor 0.24.0's streaming poll
  (`sync_trajectory`) calls only `convert_trajectory` — nothing updates
  `AgentContext` while a run is going, for any agent. Tokens and cost are
  post-run by design; only the trajectory is kept current.
- **A configured MCP server is an external dependency.** omp connects at
  startup. A server that fails its handshake was observed to warn and continue
  (`MCP server "probe" failed to connect … tools are unavailable for this
  run`); one earlier smoke cell stalled unbounded with no server process
  spawned (see DEFECTS, 2026-10-10). Nothing here retries or bounds that —
  treat a supplied server as any other external service.
- **A run with no tool call is a failed run, not a scored one.** omp exits 0
  whenever the model answers, including when it answers without acting. So after
  a 0 exit the agent checks the session for a tool call. If there is none, it
  raises Harbor's `NonZeroAgentExitCodeError`, and the trial is recorded as
  errored (and retryable) instead of being scored. The observed cause was
  OpenRouter routing the request to its **OpenInference** upstream, which
  answered as if no task had arrived — on both the Responses and the Chat
  Completions wire (`docs/worked-example.md` § 3). Exclude it with
  `compat.openRouterRouting.ignore: [OpenInference]` in a seeded
  `agent/models.yml`. A task legitimately answered in prose alone would trip
  this (tracked in issue #8); a task verified against the environment cannot
  pass without acting on it.
- **The instruction is passed as a positional argv element**, quoted by the
  agent — there is no stdin/env prompt channel.
- **File modes are not preserved** by `extra_files`; a `pre_command` that needs
  an executable does its own `chmod`.
- **The config home is wiped on every install.** Pass a `config_home` this trial
  owns.

## Development

```bash
uv sync
uv run pytest -q
uv run ruff check src tests scripts
```

The container-side recipes (install, config home, run script) are also exercised
against a real Linux container, which needs Docker and network access:

```bash
uv run python scripts/container_smoke.py
```

`VERIFY.md` lists the checks with a case that can make each one go red;
`FEEDBACK.md` lists the sensors. [`docs/spec.md`](docs/spec.md) states what the
package must do, [`docs/design.md`](docs/design.md) records the shape chosen and
the alternatives it won against, and [`docs/plan.md`](docs/plan.md) tracks the
remaining workstreams. [`docs/worked-example.md`](docs/worked-example.md) records
two real runs — a single-task acceptance trial and the 30-task data-eng-bench on
four parallel Daytona sandboxes — with the screenshots, the memory/concurrency
recipe and the foot-guns found. `AGENTS.md` and `CONTRIBUTING.md` cover
conventions.

## Licence

MIT — see [LICENSE](LICENSE).
