# Plan — harbor-omp

<!-- Created 2026-10-09 from the six workstreams the extraction was briefed with.
     Kept deliberately light until the real-trial acceptance (§ 3) closes: until
     the package has driven a real trial through Harbor's own machinery, the
     spec and design are backfilled records (see docs/spec.md, docs/design.md),
     not contracts to build against. -->

**The light-phase gate:** § 3. Until one real trial passes acceptance, work here
stays documentation and non-behavioural; no widening of the capability
declaration, no new surface.

## Status at a glance

| # | Workstream | Status | Proven by |
|---|---|---|---|
| 1 | Verify the package | ✅ done | 116 tests, ruff, format, `lint-imports` — all green |
| 2 | Container smoke | ✅ done | `container_smoke.py` on real ubuntu:24.04, exit 0 |
| 3 | Real-trial acceptance | ⛔ blocked | — (behind the harness-evals batch) |
| 4 | harness-evals cutover | ⛔ blocked | — (behind § 3) |
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

## 3. Real-trial acceptance — blocked ⭐ (the gate)

**Blocked by:** the harness-evals `baseline30b` fast-30 batch, which holds the
Daytona org's only sandbox budget (7 GiB per sandbox against a 10 GiB cap, so one
at a time). Last observed: live, `--concurrency 1`, ~4/30 pairs done, storing to
`store-daytona`. Do not attempt a concurrent trial — it dies at sandbox creation.

**When the batch clears**, run one trial against `cohort-retention-matrix` with
`--agent harbor_omp:OmpAgent`. **Acceptance:**

- `agent/trajectory.json` exists and validates (`TrajectoryValidator` clean);
- `profile_mismatches` is empty;
- tokens **≥** the incumbent's row for the same session (the delta being the
  `model_usage` records the incumbent drops);
- the verdict matches the batch row.

This is the check that would retire the spec's two `[NEEDS CLARIFICATION]`
items; it is also the first evidence that Harbor's environment class, the
`/logs/agent` mount and the upload path work with this agent.

## 4. harness-evals cutover — blocked

Lives in **harness-evals**, not here: delete `evals/harbor_agent/omp_adapter.py`
and depend on the published package. Blocked by § 3 (the batch must finish, and
the acceptance must pass first). Do not edit harness-evals while its batch runs —
it imports that repo's code and an edit splits the run.

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

1. **Check whether `baseline30b` has finished** — if it has and the sandbox is
   free, run § 3.
2. **Or proceed with § 5** (streaming first) — unblocked, no sandbox.
3. **PyPI** — needs an explicit go-ahead; nothing is published.
