# Contributing

Thanks for considering a change. This package is small on purpose: it installs
and runs one CLI under Harbor, and reads that CLI's session log. Changes that
keep it that way are welcome.

## Dev setup

```bash
git clone https://github.com/evanokeefe39/harbor-omp
cd harbor-omp
uv sync                       # creates .venv and installs harbor, pydantic, pytest, ruff
uv run pytest -q
uv run ruff check src tests scripts
```

`uv` handles the virtualenv; do not create one by hand, and do not use `pip`.

## What a good change looks like

- **A test that can fail.** Behaviour changes land with a test asserting the
  new observable behaviour (see `tests/` for the fake environment pattern — no
  Docker and no network are needed).
- **No new dependency without a reason in the PR body.** The runtime dependency
  set is Harbor and pydantic; the session reader is deliberately stdlib-only so
  other harnesses can use it without Harbor installed.
- **Docs kept honest.** If you implement something on the known-gaps list,
  flip the capability flag, update the README table, and say so in
  `CHANGELOG.md`.
- **Registers.** Add a `VERIFY.md` row (with the case that makes it red) for a
  new check; add a `FEEDBACK.md` row for a new signal.

## Tests

```bash
uv run pytest -q                       # everything
uv run pytest tests/test_run.py -q     # one module
uv run pytest -k hooks -q              # by keyword
```

The hook tests execute the agent's real run script with a POSIX shell and a
stubbed `omp`; on Windows they use Git Bash when it is installed. Tests must not
require Docker, a network, or a model key.

## Commits and pull requests

- Conventional commits: `type(scope): imperative summary` (`feat`, `fix`,
  `docs`, `test`, `refactor`, `chore`, `ci`, `build`, `perf`).
- Branch off `main` (`feat/…`, `fix/…`, …); never push to `main`. History stays
  linear — rebase, then squash-merge the PR.
- One concern per PR; keep it under ~400 lines.
- A DCO or CLA signature is **not** required.

## Reporting a defect

Open an issue with the command you ran, what happened, and what you expected.
If it is a wrong number (tokens, cache, cost), include the session JSONL shape
you saw — the metric path is the least observable part of a trial.
