# harbor-omp

A [Harbor](https://docs.harborframework.com) agent adapter for
**omp** — the coding-agent CLI shipped by the npm package
`@oh-my-pi/pi-coding-agent`. It installs a pinned omp with bun inside the trial container, runs it
under an isolated config home, records the argv it ran, and turns the omp
session log into the token, cache and cost numbers Harbor reports.

## Why this exists

Harbor ships adapters for `claude-code`, `codex`, `pi`, `opencode` and others,
but none for omp — the agent CLI this package exists to run. This package was
extracted from a private evaluation harness so the adapter could be reused
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
| `seed` | unset | Config-dir-relative path → file content, written into the isolated config dir before the agent runs. Plain data; the adapter neither reads nor renders it. |
| `config_home` | `/tmp/omp-home` | The HOME the agent runs under. `<config_home>/.omp` is the config dir (`PI_CONFIG_DIR=.omp`). Reset on every install. |
| `session_dir_name` | `omp-sessions` | Session directory under the environment log dir; `--session-dir` points at it and the post-run metrics are read from it. |
| `extra_files`, `pre_commands`, `post_commands` | unset | The extension points — see below. |

## What the adapter does

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
   launches, in install-only trials too.
5. **Reports the metrics.** After the run, the session JSONL is summed into
   `AgentContext`: input tokens (including cache), cache tokens, output tokens,
   the cost omp itself reported, the step count, and the per-model breakdown
   (`AgentContext.model_usage`) from the same pass. omp's `model_usage` events
   — an auxiliary model, for example the one behind a `find` tool — are summed
   too: they are additional to the assistant messages, and ignoring them
   under-reports a trial. Provider-reported cost is preferred; nothing is
   estimated.

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
| ATIF trajectory (`atif`) | **no** | `convert_trajectory` is not overridden, so no `logs_dir/trajectory.json` is written and no viewer/Otel/`atif2otel` consumer gets anything. This is the largest gap; the seam is `convert_trajectory` reading through `harbor_omp.session`, and the follow-up work is tracked in this repo's `CHANGELOG.md`. |
| resume / load / handoff | **no** | Harbor correctly refuses rather than pretending. |
| native config (`config=`) | **no** | Rejected at construction by Harbor (`native_config=False`). |
| skills / MCP servers | **no** | Harbor's `/harbor/skills` seam and `mcp_servers` are not read; skills instead travel as shipped config content (`config_source`/`seed`). |
| live streaming | **no** | `remote_session_logs_dir` is provided (the session dir is on the mounted log volume), but the live-conversion half of that seam is not implemented: a `--stream` job makes Harbor tar the session JSONL into `<logs_dir>/sessions/` on every poll, and `convert_trajectory` returns `None`, so no trajectory is ever produced. |

Other deliberate limits:

- **The error type Harbor reports is prose-derived.** omp runs in text mode
  (`-p`), so the output Harbor's classifier scans on a failed run is the
  agent's own prose, matched against Harbor's 34 error regexes.
  `filter_jsonl_events` cannot narrow that to harness-emitted events the way a
  JSONL-speaking adapter does, because there is no JSONL stream at exec time.
  A failed trial is still classified (and its status is omp's own), but treat
  the error type as a hint rather than as a structured field.
- **No per-exec timeout.** A hung omp runs to Harbor's task timeout rather than
  a per-execution bound.
- **The instruction is passed as a positional argv element**, quoted by the
  adapter — there is no stdin/env prompt channel.
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
`FEEDBACK.md` lists the sensors. `AGENTS.md` and `CONTRIBUTING.md` cover
conventions.

## Licence

MIT — see [LICENSE](LICENSE).
