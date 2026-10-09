# Design — harbor-omp

<!-- Backfilled 2026-10-09: the design is already implemented, so this is a
     record of the shape that was chosen and the alternatives it won against,
     not a proposal. Depth path: replacement/port (the spec's Incumbent is the
     differential). The full ceremony (diverge, ATAM review) is deferred until
     the real-trial acceptance closes — see docs/plan.md § 3. -->

## Context

The behaviour (see `docs/spec.md`) already exists in the incumbent adapter. The
design question is therefore not *what* to build but *how to package* it so the
stated reuse goal holds. The binding constraints:

- **Harbor's public API only.** The package is published; a private-harness
  import would make it unpublishable and neither side testable.
- **Everything harness-shaped arrives as data.** Benchmarks, profiles, evidence
  collectors, toolchain contracts — input, never import.
- **Small on purpose.** A published agent, not a framework.
- **uv-only, no build step.** No Node at build time; diagrams and docs must
  render from the repository alone.
- **A trial's numbers must be comparable** with the incumbent's rows, so the
  extraction may change a behaviour only deliberately and on the record.

## Alternatives considered

Ordered by how much of the incumbent they keep.

1. **Vendor the adapter into each consumer.** Each harness copies the file.
   *Rejected:* N copies drift; the incumbent's own defects (hard-coded version,
   `message.usage`-only summation) would be copied with it, and there is no
   single place to fix them.
2. **Publish a package that imports the harness modules.** *Rejected:* exactly
   the fusion this work exists to remove — it makes the package unpublishable
   and both sides untestable (`docs/architecture.md`, "The seam").
3. **Extract a standalone package whose extension points are data.** ← **chosen**
   A Harbor agent plus a stdlib-only session reader; callers pass seed content,
   run flags, a plugin checkout, extra files and pre/post commands.
4. **Rewrite from scratch against Harbor's current API.** *Rejected:* the
   incumbent encoded measured recipe facts (install shape, `--ignore-scripts`,
   the `omp/18.6.0` version string) that a rewrite would have had to rediscover,
   and the extraction was the opportunity to fix its defects rather than inherit
   them.

Within alternative 3, two sub-shapes were weighed:

- **Reader inside the agent class** vs **a separate stdlib-only module.**
  *Chosen:* separate (`session.py`). It is the piece a non-Harbor consumer
  reuses, and keeping it free of Harbor and pydantic is what lets it be tested
  and reused in isolation — enforced by a test and an `import-linter` contract.
- **Trajectory in `session.py`** vs **its own module.** *Chosen:* separate
  (`trajectory.py`). The trajectory *is* a Harbor artifact (it builds
  `harbor.models.trajectories` and gates on Harbor's validator), so it must not
  travel with the reader.

## Decisions

| # | Decision | Reason |
|---|---|---|
| D1 | Publishes as a standalone package depending on Harbor's public API only | The reuse goal; enforced by `tests/test_isolation.py` and three `import-linter` contracts |
| D2 | `session.py` and `hooks.py`/`install.py` carry no `harbor`/`pydantic` import | Reuse without Harbor; the reader must load where Harbor is absent |
| D3 | The whole option surface is `AgentConfig.kwargs` data | Nothing harness-shaped enters as an import |
| D4 | `version` is honoured, not hard-coded | The incumbent's silent no-op was a defect |
| D5 | `capabilities = AgentCapabilities(atif=True)`, everything else false | Harbor gates on the flag; a flag on without behaviour is a silent gap |
| D6 | The config home is **always reset** on install | Makes "what the trial resolved" a property of the agent, not the image — the one deliberate behaviour change vs the incumbent |
| D7 | Pre-commands are a gate, post-commands are contained | Asymmetric on purpose: a pre-spend gate must abort; a collector must never change a verdict |
| D8 | Metrics sum `message.usage` **and** `model_usage`, deduped on (model, timestamp) | The incumbent under-reported auxiliary-model tokens |
| D9 | An absent/unreadable session yields `None`, never `0` | A confident zero is indistinguishable from a free run |
| D10 | The trajectory is written only after Harbor's validator accepts it | A consumer's loader must take the file; a temporary file is validated then swapped in |
| D11 | A line that yields no step refuses the whole conversion | A shorter artifact would read as a complete one |
| D12 | Provenance records use generic names | The package may not name a benchmark |

## Risks

- **R1 — Isolation rot.** A future edit adds a Harbor import to `session.py`.
  *Mitigation:* `import-linter` contracts (contracts in `pyproject.toml`) plus
  `tests/test_isolation.py`; the red case is exercised in `VERIFY.md`.
- **R2 — Metric divergence from the incumbent.** If the two readers disagree, a
  comparison across the cutover is invalid. *Mitigation:* the `model_usage` delta
  is the known, measured difference; the real-trial acceptance (§ 3 of the plan)
  checks tokens ≥ the incumbent's row.
- **R3 — Untested against Harbor's own machinery.** The recipes are proven on
  Docker, but no `harbor run` against a task has driven them. *Mitigation:* the
  real-trial acceptance is exactly this check, and it is the gate for leaving the
  light phase.
- **R4 — Windows/Linux divergence.** A test passed on Windows and failed on
  Linux CI (`test_trajectory.py`, an ENAMETOOLONG path). *Mitigation:* the CI
  gate runs on Linux; the defect is recorded in `DEFECTS.md`-adjacent history in
  the PR that fixed it.
- **R5 — The incumbent keeps drifting.** harness-evals still runs the old
  adapter while this package is developed. *Mitigation:* the cutover (plan § 4)
  is deferred until the batch finishes, and the two readers are compared on real
  trials before it lands.

## Migration and rollback

**Migration.** The package is additive: it does not touch the incumbent until the
harness-evals cutover (plan § 4). That step deletes
`evals/harbor_agent/omp_adapter.py` and points the batch at
`harbor_omp:OmpAgent`. Landing order: this package green → one real trial
compared against the incumbent's row → cutover.

**Rollback.** Revert the cutover commit; the incumbent file is restored from
history. No data migration is involved — the packages are independent
distributions.

## Tasks

Dependency-ordered; each carries its verification signal. These are the
*engineering* tasks; the project-level workstreams (1–6) live in
`docs/plan.md`.

1. Verify the package green — `uv run pytest -q`, `ruff check`, `ruff format
   --check`, `lint-imports`. **Signal:** 116 passed, all gates clean.
2. Container smoke — `uv run python scripts/container_smoke.py`. **Signal:**
   `container smoke: all expected evidence present`, exit 0. *(done)*
3. Real-trial acceptance on `cohort-retention-matrix` with
   `--agent harbor_omp:OmpAgent`. **Signal:** `agent/trajectory.json` validates,
   `profile_mismatches` empty, tokens ≥ the incumbent's row, verdict matches the
   batch row. *(blocked — plan § 3)*
4. harness-evals cutover. **Signal:** the batch runs green with the package
   installed and the incumbent file deleted. *(blocked — plan § 4)*
5. Close the README gaps (resume/load/handoff, native `config=`, skills/MCP).
   **Signal:** each is either implemented with a red-case test or documented with
   its reason, and the README table matches the code. *(open — plan § 5)*
