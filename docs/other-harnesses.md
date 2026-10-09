# Using harbor-omp from another harness

The brief for this package named two non-Harbor consumers — ADE-Bench's
`AbstractInstalledAgent` and ELT-Bench's `agents/run.py`. **Neither was read
while writing this document `[INFERENCE]`** — the integration points are
described from their names, so treat the specifics as a starting point, not as
verified instructions. What was verified here is which parts of this package
stand alone; the tests prove it.

## What travels without Harbor

| Piece | Import | Why it is reusable |
|---|---|---|
| `harbor_omp.session` | `from harbor_omp.session import sum_session_usage` — or load the file directly | stdlib only, no Harbor, no pydantic: it sums a directory of omp session JSONL into tokens, cache, cost and steps |
| `harbor_omp.install` | `from harbor_omp.install import install_command, version_command` | the bun + pinned-install shell recipe and its version probe, as strings |
| The run argv shape | `OmpAgent._run_argv` (or the constants in `options.py`) | the omp invocation a container needs: `-p --auto-approve <flags> --session-dir=… --model=…` |
| The hook semantics | `docs/architecture.md`, `harbor_omp/hooks.py` | pre-commands as a gate and post-commands as best-effort is a design that transfers to any harness with a shell |

## What does not travel

`OmpAgent` itself is a Harbor class. A non-Harbor harness should reuse the
recipes above and keep its own lifecycle: the interesting parts are the
container-side script and the session reader, not the base class.

## A non-Harbor consumer, in outline

1. Install omp in your sandbox with `install.install_command(spec)`.
2. Put your own config into `$HOME/.omp` (or ship a checkout and extract it
   there), and run the agent with `HOME`/`PI_CONFIG_DIR=.omp` set, with the argv
   shape above, capturing output and the process status.
3. After the run, copy the session directory out and read it with
   `sum_session_usage`; `None` means "no session was written", which is not the
   same as zero tokens.

## If you build an adapter for another harness

Two properties are worth keeping, because they are what makes a trial
comparable:

- **Record the argv before the agent launches.** An identity record that exists
  even for a failed run is what lets two trials be compared row by row.
- **Never let the collector change the agent's exit code.** Collection that can
  alter a verdict makes every later comparison suspect.
