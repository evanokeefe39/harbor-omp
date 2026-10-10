# Plan — harbor-omp

<!-- Created 2026-10-09 from the six workstreams the extraction was briefed with.
     Kept deliberately light until the real-trial acceptance (§ 3) closes: until
     the package has driven a real trial through Harbor's own machinery, the
     spec and design are backfilled records (see docs/spec.md, docs/design.md),
     not contracts to build against. -->

**The light-phase gate: § 3 — cleared 2026-10-09.** A real trial now passes
acceptance (see § 3), so the light phase is over: the spec and design graduate
from backfilled records to contracts, and behavioural work — § 4, and § 5's
either/or closes — is now in scope. The one caveat is the silent no-op trials
found in the 30-task run (`docs/worked-example.md` § 3): they are a **defect to
fix**, not an accepted limitation, and no pass/fail rate is trustworthy until
they are excluded.

## Status at a glance

| # | Workstream | Status | Proven by |
|---|---|---|---|
| 1 | Verify the package | ✅ done | 116 tests, ruff, format, `lint-imports` — all green |
| 2 | Container smoke | ✅ done | `container_smoke.py` on real ubuntu:24.04, exit 0 |
| 3 | Real-trial acceptance | ✅ done | acceptance trial, 2 GiB Daytona sandbox ([run record](worked-example.md#2-the-acceptance-trial)) |
| 4 | harness-evals cutover | ⬜ open | — (unblocked: § 3 passed; needs a kwargs mapping layer) |
| 5 | README gaps | ⬜ open | — (unblocked) |
| 6 | Publishing | ✅ done | public repo, 3 PRs merged, CI green |

## 1. Verify the package — done

```bash
uv sync && uv run pytest -q            # 116 passed
uv run ruff check src tests scripts    # clean
uv run ruff format --check src tests   # clean
uv run lint-imports                    # 3 kept, 0 broken
```

Re-run before trusting any change; if the counts differ, stop and reconcile.

## 2. Container smoke — done

```bash
uv run python scripts/container_smoke.py   # needs Docker + network; agent is stubbed
```

Proves the container-side recipes on real Linux: the install leaves a working
`omp` on PATH, the seed lands at `<config_home>/.omp/<relpath>`, the CLI runs
under the isolated `HOME`/`PI_CONFIG_DIR`, and the run script reports the agent's
status even when a post-command exits 0. Last run: **passed**, `all expected
evidence present`.

Docker Desktop's daemon is often down — start it and confirm `docker ps` answers
before concluding the smoke is unavailable.

## 3. Real-trial acceptance — done ⭐ (the gate)

One trial, `cohort-retention-matrix`, `--agent harbor_omp:OmpAgent`, on a Daytona
sandbox at **2 GiB** (`override_memory_mb: 3000` → Daytona floors to 2 GiB).
Full record: [`docs/worked-example.md`](worked-example.md).

**Acceptance:**

- ✅ `agent/trajectory.json` exists and validates — 962,818 bytes, ATIF v1.8,
  `validate_trajectory` → True, 106 steps;
- ⚠️ **`profile_mismatches` does not apply to a standalone run** — that field is
  produced by the harness-evals evidence collector, which this package does not
  provide. The criterion was written for a store row; it is dropped here, not
  silently passed;
- ✅ tokens **≥** the incumbent's row (1,718,691 vs 1,661,951);
- ✅ the verdict matches the batch row (both `fail`, reward 0).

Other observed numbers: `n_errored_trials: 0`, verifier 23/24 pytest,
**$0.074** provider-reported cost, zero OOM at 2 GiB.

This is the evidence that Harbor's environment class, the `/logs/agent` mount
and the upload path work with this agent. It also leaves one caveat that the
spec's `[NEEDS CLARIFICATION]` items do **not** fully retire: a standalone run
has no `profile_mismatches` signal, and a later 30-task run surfaced silent
no-op trials — **22 of 30** (`docs/worked-example.md` § 3) — that must be
excluded before any pass/fail rate is trusted. The run itself was clean:
30/30 trials in 46 m 13 s at four-in-flight, $0.43, 2 passed.

## 4. harness-evals cutover — open, unblocked

Lives in **harness-evals**, not here: delete `evals/harbor_agent/omp_adapter.py`
and depend on the published package. § 3 now passes, so this is unblocked — but
it is **not an import-path swap**: `evals/runners/run_trial.py`'s
`build_job_config()` emits the fused adapter's kwarg names (`profile_seed`,
`omp_config`, `router_plugin`) while this package uses `seed`, `config_source`,
`plugin` (`run_flags` and `thinking` already match). A mapping layer is
required. Do not edit harness-evals while a batch of its own is running — it
imports that repo's code and an edit splits the run.

## 5. README gaps — open, unblocked

The README's "Capabilities and known gaps" table declares four gaps. Each closes
either by implementing it (with a red-case test) or by documenting *why* it stays
`no` — the second is an acceptable outcome, not a failure. No sandbox needed.

| Gap | Declared | The work |
|---|---|---|
| live streaming | **partly** | The trajectory streams; `AgentContext` is filled post-run. Either finish the metrics half or **narrow the README claim** to match the code |
| resume / load / handoff | **no** | Implement against Harbor's contract, or state why the omp session format does not support it. "Keep `no`, document the reason" is a valid close |
| native config (`config=`) | **no** | Rejected at construction (`native_config=False`). Decide whether the native seam is reachable from omp; if not, document the rationale |
| skills / MCP servers | **no** | Harbor's `/harbor/skills` seam and `mcp_servers` are unread; skills travel as shipped config content. Same either/or as native config |

Order: **streaming first** (it is the one already half-built), then
resume/load/handoff, then native config / skills / MCP.

## 6. Publishing — done

The public repo exists (`github.com/evanokeefe39/harbor-omp`), `main` is the
default branch, CI runs on every push/PR, and three PRs have merged. **PyPI is
not published** — `uv add harbor-omp` in the README is aspirational until it is.
That step needs an explicit go-ahead.

## Landed this session (context for the statuses above)

| Commit | What |
|---|---|
| `71eecb9` | `ci(boundaries)` — `import-linter` gate over the isolation contracts |
| `3f7e2a1` | `docs(vocabulary)` — "adapter" → "agent" per Harbor's own terms (PR #1) |
| (PR #1) | `test(trajectory)` — fixed a Linux-only ENAMETOOLONG defect CI exposed |
| `229050b` | `chore(docs)` — dropped the speculative `other-harnesses.md`; ignored `.env` (PR #2) |
| `8ef5b62` | `docs(architecture)` — lifecycle rendered as a Mermaid sequence diagram (PR #3) |

## Next actions

1. ~~**Fix the silent no-op trials**~~ — done 2026-10-10. Root cause is upstream
   (OpenRouter Responses API × OpenInference; `docs/worked-example.md` § 3). The
   agent now raises a run with no tool call as a failed agent run instead of
   letting it be scored.
2. **§ 4 cutover** — unblocked, but needs the kwargs mapping layer named there.
3. **§ 5 README gaps** — streaming first; no sandbox needed.
4. **PyPI** — needs an explicit go-ahead; nothing is published.
