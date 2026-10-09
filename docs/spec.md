# Specification — harbor-omp

<!-- Backfilled 2026-10-09 from the implemented package, the incumbent adapter's
     own docstring, and the registers. Written *after* the code (the skill
     allows this only when it is labelled): see "Provenance" at the end.
     Kept deliberately light until the real-trial acceptance (docs/plan § 3)
     closes. -->

## Intent

Harbor ships agents for `claude-code`, `codex`, `pi`, `opencode` and others, but
none for **omp** (the coding-agent CLI shipped by `@oh-my-pi/pi-coding-agent`).
A Harbor job author who wants to run omp as a trial agent — and read back its
token, cache and cost numbers plus an ATIF trajectory — has no supported way to
do it.

This package is that agent: a Harbor agent, selected by import path, that
installs a pinned omp inside the trial container, runs it under an isolated
config home, records what it ran, and reports the session's metrics. Its second
purpose is to be **reusable**: it was extracted from a private evaluation
harness, and everything benchmark- or harness-shaped must arrive as *data*
rather than as an import. Reuse within the original harness and by a
non-Harbor consumer is a stated goal, not a side effect.

## Incumbent

A working implementation of this behaviour already exists: the omp adapter in
the private harness-evals repo (`evals/harbor_agent/omp_adapter.py`), from which
this package was extracted. Its own module docstring is the differential below.
Every demonstrated mechanism it had is walked here with a disposition.

| Incumbent mechanism | What it did | Disposition |
|---|---|---|
| pinned omp version | **hard-coded** `@oh-my-pi/pi-coding-agent@18.6.0`; `version=` was a silent no-op | **replaced-with-parity** — now an honoured option (`DEFECTS.md`, first upstream row); a bare `18.6.1` normalises to the omp package |
| run flags | derived by **importing** `evals.profiles.profile.run_flags` | **replaced-with-parity** — the `run_flags` option carries them verbatim; unset means the minimal-extension default |
| session dir | `/logs/agent/omp-sessions` via `--session-dir` | **preserved** (`session_dir_name` option) |
| metrics source | summed `message.usage` only | **preserved, extended** — also sums `model_usage` events, which the incumbent silently dropped (`DEFECTS.md`, third row) |
| profile home | wiped and rebuilt at `/tmp/profile-home/.omp` | **replaced-with-parity** — `config_home` option, **always reset** on install (the one deliberate behaviour change) |
| router plugin | verified clean, archived from committed HEAD, uploaded, extracted | **preserved** (`plugin` option) |
| shipped config content | `omp_config` (skills, rules, custom agents, global context, hooks) | **replaced-with-parity** — `config_source` + `config_paths` |
| toolchain contract | imported `evals.harbor_agent.toolchain`; any missing binary aborted | **deliberately dropped** — the package may not know a toolchain. A caller attaches the probe as a `pre_command`, which is *also* a gate (non-zero aborts before spend) |
| provenance records | `run-flags.json`, `omp-config-source.json`, `toolchain.json` | **preserved** (renamed to generic names): `run-flags.json`, `config-source.json` |
| `PYTHONPATH` coupling | adapter added to `PYTHONPATH` at the environment level | **deliberately dropped** — the published package resolves by import path alone |
| install-only gate | `install_only=True` records argv, runs nothing | **preserved** |
| ATIF trajectory | **none** | **added** (not a drop) — the incumbent had no trajectory; this package implements one |

Measured hazard notes carried from the incumbent's comments: `--ignore-scripts`
blocks two postinstalls; `omp --version` prints `omp/18.6.0` (the product prefix
is part of the output, so `AgentInfo.version` reads `omp/18.6.0`).

## Behavioral Contracts

1. **Install.** GIVEN a task environment, WHEN `setup()` runs, THEN bun and the
   npm spec of `version` are installed and `omp --version` is probed.
2. **Isolation.** WHEN the agent runs, THEN `HOME=<config_home>` and
   `PI_CONFIG_DIR=.omp`, and the operator's own `~/.omp` is never read.
3. **Reset before seed.** WHEN `setup()` runs, THEN `<config_home>/.omp` is
   emptied *before* the seed, the shipped config tar and the plugin land in it.
4. **Pin before spend.** GIVEN a `config_source`/`plugin` checkout with
   uncommitted changes to a tracked shipped path, WHEN `setup()` runs, THEN it
   aborts **before any upload** and before any model spend.
5. **argv recorded.** WHEN `run()` is entered, THEN the exact argv is written to
   `/logs/agent/resolved/run-flags.json` **before** omp launches.
6. **Zero-spend gate.** WHEN `install_only` is set, THEN the argv is recorded and
   neither the agent nor any hook command runs.
7. **Pre-command is a gate.** GIVEN `pre_commands`, WHEN one exits non-zero, THEN
   the run aborts before the agent starts.
8. **Post-command cannot decide.** WHEN `post_commands` run, THEN they run in one
   subshell and **cannot** change the agent's exit status, in either direction.
9. **Status propagation.** WHEN omp exits with status *N*, THEN the run reports
   *N* unchanged.
10. **Metrics.** WHEN the run ends, THEN `AgentContext` carries input tokens
    (cache-inclusive), cache tokens, output tokens, omp's own reported cost, the
    step count, and the per-model breakdown — summed from both `message.usage`
    and `model_usage` records.
11. **Absent is not zero.** WHEN no session JSONL exists, or none of it could be
    read, THEN the metrics are **absent** (`None`), never a confident `0`.
12. **Trajectory.** WHEN the run ends, THEN `logs_dir/trajectory.json` is written,
    put through Harbor's own `trajectory_validator` before it lands, with one
    step per non-blank session line carrying that line's payload.
13. **Accounting refusal.** WHEN a session line yields no step, THEN the whole
    conversion is refused (no shorter artifact) and the trial's metrics — read
    from the session first — are left alone.
14. **Capability honesty.** `capabilities` declares only what is implemented; a
    flag is true only because the behaviour behind it exists.

## Edge Case Inventory

- **Unreadable or absent session dir** → `None`, not zero (contract 11).
- **Torn / undecodable line** → counted (`skipped_lines`), never dropped
  silently; the accounting view reports every non-blank line.
- **Non-numeric usage value** → counted (`skipped_values`), never raised
  (`DEFECTS.md`, second upstream row).
- **`model_usage` record already covered** by a message's (model, timestamp) →
  not double-counted.
- **`config_home` already populated** with foreign data → wiped (contract 3).
- **Trailing-slash pathspec** in `config_paths` → must match, not false-positive
  "missing at HEAD" (`DEFECTS.md`, first row).
- **Seed bytes** → preserved exactly, no host CRLF translation
  (`DEFECTS.md`, second row).
- **Post-command `exit N` / `EXIT` trap / `set -e`** → contained by the subshell.
- **`plugin` set while `run_flags` is unset** → refused at construction (the
  default `--no-extensions` also gates plugin loading).
- **Blank `version`** → refused before any container command.

## Negative Space

**Must not:** import a benchmark, profile or harness module; read the operator's
`~/.omp`; claim a version it did not measure; claim a capability it does not
implement; publish a missing metric as a confident zero; let a post-command
change a verdict.

**Out of scope** (declared `no`/`partly` in the README): resume/load/handoff,
native `config=`, the skills/MCP seam, a per-exec timeout, streaming
`AgentContext` (only the trajectory streams).

**Reserved for human review:** publishing (PyPI, public remote) and any widening
of the capability declaration.

## Open Questions

- **[NEEDS CLARIFICATION]** Does a real trial through **Harbor's own machinery**
  (its environment class, the `/logs/agent` mount, the upload path) work? The
  container-side recipes are proven on Docker and the documented invocation
  resolves with `--print-config`, but no `harbor run` against a task has been
  driven. This is the acceptance gate for leaving the "light" phase — see
  `docs/plan.md` § 3.
- **[NEEDS CLARIFICATION]** Is post-run-only `AgentContext` acceptable, or must
  metrics stream alongside the trajectory? Currently the trajectory streams and
  the metrics do not (`README.md`, live-streaming row).

## Quality Scenarios

- **Cost:** zero model spend on an install-only run and on a failed
  pre-command gate.
- **Comparability:** a trial's reported tokens are **≥** the incumbent's for the
  same session (the delta being the `model_usage` records the incumbent drops).
- **Traceability:** a consumer holding only `trajectory.json` can reconstruct
  the session line by line.

## Provenance

Written 2026-10-09 by backfilling the implemented package, the incumbent
adapter's docstring, and the four registers — **after** the code, which the
`pb-spec` skill permits only when labelled. It is therefore a *record of what
was built*, not a pre-agreed contract; the Open Questions above are the points
where that distinction still matters. Kept light on purpose until the real-trial
acceptance closes; a full pass (with an independent `doc-reviewer`) is deferred
to that point rather than run now.
