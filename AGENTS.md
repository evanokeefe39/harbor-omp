# AGENTS.md — working in harbor-omp

Conventions for agents (and people) changing this repo. The point of this file
is that a contributor can make a correct change without re-deriving the rules.

## What this repo is

A standalone Harbor agent for the `omp` CLI. It depends on Harbor's
public API and on nothing else. **If a change would make the package import
anything from a private eval harness, it is wrong** — that coupling is the thing
this repo exists to remove. `tests/test_isolation.py` enforces it.

## Ground rules

- **uv only.** `uv sync`, `uv run pytest`, `uv run ruff check src tests
  scripts`. Never `pip install`; never a bare `python`.
- **Never edit a consumer's repo.** `harbor-omp` is consumed by other repos; a
  change here is published, not patched in place.
- **Test-first for behaviour.** A behavioural change lands with the test that
  can go red without it. Assert observable behaviour (argv, uploaded bytes,
  recorded status, returned values), never source text, defaults or wiring.
- **A check that cannot go red proves nothing.** Every row added to `VERIFY.md`
  names the input or edit that makes it fail.
- **Do not claim more than the code does.** `capabilities` is a promise Harbor
  gates on; a flag turned on without the behaviour behind it is a silent
  capability gap, and is treated as a defect.

## Branch, commit, PR

- Branch from `main`: `feat/…`, `fix/…`, `docs/…`, `refactor/…`, `test/…`.
- Conventional commits, several `-m` flags when the body earns it:
  `type(scope): imperative summary`. Never a bare commit, never a commit to
  `main` directly, no merge commits.
- Bump `version` in `pyproject.toml` in the same PR as a shipped change:
  `fix`/`perf` → patch, `feat` → minor, breaking → minor while pre-1.0, major
  after. Docs/CI/test-only changes do not bump.

## Registers

| File | Holds | Append rule |
|---|---|---|
| `VERIFY.md` | checks, one row per check, with a red case | when a check is added, changed or retired |
| `FEEDBACK.md` | sensors, one row per signal | when a signal is added or stops being read |
| `DEFECTS.md` | append-only defect ledger | when a defect is found, with its evidence |
| `CHANGELOG.md` | observation-cycle ledger | when an observation cycle closes |

Never rewrite an existing row to make history look better; append.

## The container contract

The agent writes only under `/tmp` and the environment log dir
(`/logs/agent`). If a change needs a write anywhere else in the task container,
say why in the commit body — the trial workspace must be touched only by the
agent itself.

## Before opening a PR

1. `uv run pytest -q` green.
2. `uv run ruff check src tests scripts` clean.
3. Registers updated for the change.
4. `README.md` known-gaps table still true (flipping a capability means editing
   both).
