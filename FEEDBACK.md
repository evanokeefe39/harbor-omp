# Feedback catalogue — harbor-omp

<!-- schema: FEEDBACK v2 (2026-09-27): signal|where-it-lands|why-when-useful|cadence -->
<!-- markdown table, deliberately: a row lands in the commit's diff beside the work it
describes, so `git log -p` on this file relates when a sensor was added or retired -->
<!-- the column definitions and append rules live in skill://imp-feedback -->

Lifecycle stages this ledger covers: author → install → eval run → PR + review → monitor. (No published-release stage yet: the package has never been released.)

## Catalogue

| signal | where it lands | why / when it's useful | cadence |
|---|---|---|---|
| skipped session input (`SessionUsage.skipped_files` / `skipped_lines` / `skipped_values` / `unattributed_records`) | the return value, and a warning line from `populate_context_post_run` ("the totals below may be low") | a rising count means the reader and the writer have diverged — a new omp version, a torn write, or a field that changed type — and the token totals for those trials cannot be trusted. `unattributed_records` in particular separates "the totals are right" from "the per-model breakdown is missing a record" | per trial, post-run |
| missing session JSONL (`sum_session_usage` returns `None`) | the same function, with a warning naming the directory | the trial reports no tokens and no cost at all; a rate above zero means omp is not writing where the adapter reads, which silently degrades every comparison built on cost | per trial, post-run |
| step count (`AgentContext.metadata["omp_steps"]`) | the trial's agent context | zero steps with a non-zero exit status is a failed launch; zero steps with status zero is a trial whose instruction did nothing — the two need different responses | per trial, post-run |
| per-model usage (`SessionUsage.models` → `AgentContext.model_usage`) | the trial's agent context, beside the totals | names which models the tokens went to, including an auxiliary model omp reports through a `model_usage` event (a `find` tool, a `typesafe` role). A model missing here while the totals are non-zero means a usage record could not be attributed, and a materially growing auxiliary share means the trial's cost is drifting away from the main model's | per trial, post-run |
| cost absence (`cost_usd is None` while tokens are non-zero) | the trial's agent context | "omp reported no cost" is a fact about the provider path, not a free run; comparing it as 0.0 is the defect this signal prevents | per trial, post-run |
| recorded argv (`/logs/agent/resolved/run-flags.json`) | the container log dir, read back with the trial | the identity of what ran, written before the agent launches and also in an install-only trial: two trials whose rows differ only in verdicts can be shown to have run different flags | per trial |
| measured CLI version (Harbor's `AgentInfo.version`, from `omp --version`) | the trial record | shows what the container actually has, next to the pin the caller asked for: a pin that did not land (a registry or cache surprise) becomes visible instead of inferred | per trial, post-install |
| shipped-source commits (`plugin-source.json`, `config-source.json`) | the container's resolved dir | which plugin and config commits a run used; a dirty or missing tree aborts before these are written, so their presence is itself the "the pin landed" signal | per trial, install |
| pre-command abort (`harbor-omp: pre-command failed (rc=…)`) | the run's stderr, and the trial's failed status | an environment that fails its own gate is the intended failure mode; a cluster of them means the environment moved, not the agent | per trial, on failure |
| post-command failure (`harbor-omp: post-command failed (rc=…)`) | the run's stderr, while the trial's status is unchanged | the most dangerous silent degradation: collection stopped working and the trial still looks normal. Watch this line as a rate, not per trial | per trial, post-run |
| upload targets (`RecordingEnvironment.uploaded` in tests; the container's file list in a trial) | test assertions, and a trial's log dir | proves a hook's files really arrived — a hook that silently received nothing would otherwise produce a plausibly empty result | per test run; per trial when a collector is attached |
