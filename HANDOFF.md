# HANDOFF — OmpAgent supplies the eval config by ref (SOLO-265)

Handed off 2026-10-13. Branch `feature/solo-265-omp-config-by-ref`, cut from
`main` at `2364e41`. Receiver: read this, then run the step-0 gate below.

## Goal

The eval config (omp's skills, rules, agents, hooks, `models.yml`, `AGENTS.md`)
is currently **651 files copied verbatim from `~/.omp` into a sibling repo**
(`harness-evals/evals/profiles/production/`) and shipped from that copy. It must
instead be supplied from `omp-home` **by ref**, so the pin is a commit rather
than a byte copy, and a stale copy becomes impossible.

This repo owns the agent half. The `harness-evals` half is separate.

## Definition of done

- [ ] A run supplies the config from a `omp-home` checkout pinned to a ref —
      done when `run-flags.json` / the config source record in a trial's logs
      names an `omp-home` **commit**, not a path inside `harness-evals`.
- [ ] A wrong ref or a missing pinned path **fails loudly at install**, before
      any model spend — done when pointing at a bad ref aborts with a named
      error and no container work.
- [ ] omp's existing config flags are reachable from the job config without a
      new flag being invented — done when `--ak` carries them and `omp --help`
      is unchanged.
- [ ] omp's API key is declared, not hardcoded — done when `api_key_envs` names
      it and `--env-file` carries it.
- [ ] The four gates pass: ruff, mypy, import-linter, pytest.
- [ ] `docs/design.md` and `docs/spec.md` describe the shipped behaviour.

## Step-0 gate (do this first, before any new work)

```bash
git fetch && git checkout <SHA recorded below>
python -c "import harbor_omp, inspect; print(inspect.getsourcefile(harbor_omp))"
grep -n "archive_git_head" src/harbor_omp/omp_agent.py
```

**Last completed step to verify:** `_ship_config()` pins by archiving host-git
`HEAD` (`archive_git_head(src, what="the config content", pathspecs=paths)`),
uploads the tar, and records `{"commit", "src", "paths"}` — aborting before any
upload when the source cannot be pinned. Report PASS or the discrepancy.

## Current state

- Branch `feature/solo-265-omp-config-by-ref` off `main` (`2364e41`), **clean**.
- **No code changes made in this repo yet.** This handoff carries context, not
  work-in-progress.
- Recorded SHA at handoff: see the commit that added this file.

## The finding that reframes the work

Read `src/harbor_omp/omp_agent.py:289-403` before planning anything.

**`OmpAgent` already pins by ref.** `_ship_config()`:

- takes `config_source` as a **host path to a git checkout**,
- runs `archive_git_head(src, pathspecs=config_paths)` → `(commit, tar_bytes)`,
- uploads the tar and a JSON source record `{commit, src, paths}`,
- and the install docstring states: *"Any source that cannot be pinned aborts
  here, before any upload and before any model spend."*

**So the agent is not the thing that needs building.** The copy exists because
`harness-evals` chose to hand the agent a host path it controls, and populated
that path by copying bytes out of `~/.omp`. The defect is the **host-side
population**, not the agent's pinning.

**Corollary worth checking:** when `config_source` points at a copy inside
`harness-evals`, `archive_git_head` resolves `HEAD` of the **`harness-evals`**
repo — so the recorded commit is not the content's provenance. If that is what
the trials recorded, it is a provenance defect in its own right.

## Next steps (ordered, each with its acceptance check)

1. **Settle where the clone happens.** `config_source` is a *host* path, but
   `install()` runs *in the container*. Two shapes:
   - **(a) host-side clone** — a `pre_command` clones `omp-home` at a ref into a
     host path; `config_source` points at it. Note `6ec8d81 feat(run): run
     pre_commands in install-only trials` already landed, so the hook exists.
   - **(b) container-side clone** — `install()` clones inside the container and
     `config_source` stops being the input.
   Check `docs/spec.md` for which the current `config_source` contract implies.
   *Done when:* the chosen shape is written in `docs/design.md` with the reason.
2. **Make the ref an input**, whatever the shape — an `--ak` value, not a
   constant. *Done when:* a trial's source record names the commit that was
   asked for.
3. **Declare omp's own surfaces** rather than inventing any:
   `api_key_envs=("OPENROUTER_API_KEY",)` and `CliFlag`s for omp's existing
   config flags. *Done when:* `--ak`/`--env-file` carry them and nothing new
   appears in `omp --help`.
4. **Prove the failure path.** *Done when:* a bad ref aborts at install with a
   named error, before any container command and before any model spend.
5. **Gates + docs.** *Done when:* the four gates pass and `docs/design.md` /
   `docs/spec.md` match the shipped behaviour.

## Key file paths

| path | why |
|---|---|
| `src/harbor_omp/omp_agent.py:224` | `class OmpAgent(BaseInstalledAgent)` |
| `src/harbor_omp/omp_agent.py:289` | `install()` — already aborts early on an unpinnable source |
| `src/harbor_omp/omp_agent.py:364` | `_ship_config()` — the ref-pinning that already exists |
| `src/harbor_omp/omp_agent.py:120` | `_git(*args)` helper already present |
| `src/harbor_omp/install.py` | install commands, `SYSTEM_DEPENDENCIES`, version probe |
| `src/harbor_omp/options.py` | `OmpOptions` — where a ref input would land |
| `src/harbor_omp/hooks.py`, `session.py`, `trajectory.py` | extension points, session JSONL, ATIF |
| `docs/spec.md`, `docs/design.md`, `docs/architecture.md` | contracts to update |
| `docs/plan.md`, `docs/worked-example.md` | context |
| `scripts/capability_smoke.sh`, `scripts/container_smoke.py` | smoke harness |
| `scripts/omp_provider_repro.sh` | provider reproduction |

## Decisions made and constraints discovered

- **No new CLI flag.** Harbor's `BaseInstalledAgent` already has the surfaces:
  `install()` (abstract), `config_source` (host path or inline JSON),
  declarative `CliFlag`/`EnvVar` → `--ak`/`--ae`, and `api_key_envs`. A private
  `--profile` would be the same false abstraction as the `checks.py` and
  `profile.py` that were deleted from `harness-evals`.
- **The clone pattern is Harbor's own.** `harbor/agents/installed/swe_agent.py`
  ships `_build_clone_command(repo_url, destination, version)` with
  branch→tag→commit resolution; `deerflow.py` clones the same way.
- **No container image.** GHCR storage and bandwidth are free for private
  packages too, so publishing buys ~$0, while an image adds either a registry
  token in the sandbox or full exposure of the content.
- **Secrets are a declared surface.** `_collect_launch_job_secrets` in Harbor's
  `cli/hosted_jobs.py` turns every `--env-file` key into a job-scoped credential:
  encrypted, injected per trial, revoked at job end, **names only** displayed.
  So a private `omp-home` + a token in `--env-file` is a clean option, not a
  credential loose in the sandbox.
- **Measured, not assumed:** 650 of the 651 copied files are tracked in
  `omp-home`; the exception is `agent/agents/task.md`, the seed that
  `harness-evals` renders.
- **Branch naming:** this repo's guard rejects `handoff/…`; use the Linear kind
  prefix (`feature/solo-265-…`). The handoff skill's naming is overridden here.

## Open questions / risks

- **Which clone shape (host vs container)** — the load-bearing one. Settle it
  against `docs/spec.md` before writing code.
- **Public `omp-home`, or a token in `--env-file`?** A strategy call, not a
  technical one; the secret mechanism is clean either way.
- **Does `archive_git_head` currently record `harness-evals`' HEAD** when the
  source is a copy inside that repo? If yes, that is a provenance defect.
- **Network in the sandbox:** a container-side clone needs GitHub reachable.
  The dataset already clones by ref, and Daytona's allow-list carries GitHub.

## How to verify

```bash
uv run ruff check .
uv run mypy .
uv run lint-imports
uv run pytest -q
bash scripts/capability_smoke.sh
```

Trial evidence lands in the trial's logs dir; the config source record is the
JSON naming `{commit, src, paths}` — that file is the proof of pinning.

## Data state

Not applicable — this workstream moves no data. It changes how a config
directory is populated on the host. No backfill, no write target, no
downstream consumer, nothing in flight.

## Explicitly not in this doc

No secrets, no absolute paths, no hostnames, no usernames, no sample rows, no
transcripts, no connection strings. Data sources are named logically.
