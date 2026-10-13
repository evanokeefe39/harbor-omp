# HANDOFF — OmpAgent supplies the eval config (SOLO-265)

Handed off 2026-10-13, **revised** after the research in `docs/`. Branch
`feature/solo-265-omp-config-by-ref`, cut from `main` at `2364e41`. Receiver:
read this, then run the step-0 gate below.

> **This revision replaces an earlier one.** The first version framed the open
> question as "host-side clone vs container-side clone". That was the wrong
> fork — both options assumed the directory should be shipped at all. The
> research below shows no installed agent ships one.

## Goal

The eval config (omp's skills, rules, agents, hooks, `models.yml`, `AGENTS.md`)
is currently **651 files copied verbatim from `~/.omp` into a sibling repo**
(`harness-evals/evals/profiles/production/`) and shipped from that copy. It must
instead come from `omp-home` **by ref**, so the pin is a commit rather than a
byte copy, and a stale copy becomes impossible.

This repo owns the agent half. The `harness-evals` half is separate.

## Step-0 gate (do this first, before any new work)

```bash
git fetch && git checkout d89183d    # the verified research commit; or the branch tip, which adds this file
grep -n "native_config" ../../.venv/Lib/site-packages/harbor/agents/installed/base.py
grep -rn "native_config" src/harbor_omp/          # expect NOTHING
grep -rlE "git archive|tarfile" ../../.venv/Lib/site-packages/harbor/agents/installed/   # expect NOTHING
grep -n "native_config" ../../.venv/Lib/site-packages/harbor/agents/installed/claude_code.py ../../.venv/Lib/site-packages/harbor/agents/installed/codex.py
```

**Claims to verify:** (1) `base.py:620` raises when config is passed and
`capabilities.native_config` is false; (2) `OmpAgent` declares `native_config`
nowhere; (3) no installed agent uses `git archive` or `tarfile`; (4)
`claude_code` and `codex` — the only two `config_source` users — both declare
`native_config=True`. Report PASS or the specific discrepancy.

## Read these first

Both were produced this session against Harbor 0.24.0 and are committed here:

- **`docs/established-patterns.md`** — survey of all 39 installed agents, 433
  `file:line` citations, real grep counts. The convention index is the useful part.
- **`docs/agent-comparison.md`** — six-way comparison of `claude_code`, `codex`,
  `hermes`, `pi`, `opencode`, `gemini_cli` (the agents the user named), with a
  seventh column for `OmpAgent`.

`pi.py` is the nearest relative: omp (oh-my-pi) is an offshoot of pi, and both
declare `MODEL_CONNECTION = ModelConnectionSpec(passthrough=True)`.

## Current state

- Branch `feature/solo-265-omp-config-by-ref` off `main` (`2364e41`).
- Commits: `be4778a` HANDOFF (superseded by this revision), `119503a`
  `docs/established-patterns.md`, `d89183d` `docs/agent-comparison.md`. **The
  tip of this branch is this revision** — a commit cannot name its own hash, so
  pin to `d89183d` (verified content) or to the tip (adds this file).
- **No code changes made in this repo.** This handoff carries context, not
  work-in-progress. The design is unsettled by design — settle it before coding.

## The findings that reframe the work

**1. `config_source` is a name collision, and Harbor's own path raises for us.**

```python
# base.py:620
if config is not None and not self.capabilities.native_config:
    raise ValueError(f"Agent '{self.name()}' does not support config. You can implement it.")
```

`claude_code.py:119` and `codex.py:127` declare `native_config=True`, and those
are exactly the agents that use `config_source`. `OmpAgent` declares it nowhere,
so its `config_source` *option* shares a name with Harbor's *property*, never
interacts with it, and Harbor's mechanism is inert here.

**2. `git archive` has no precedent — 0 of 38.**

`OmpAgent._ship_config()` (:364) archives a local checkout via `git archive`
(:98-181) and extracts it in-container (:548-563). No installed agent does this.
Config delivery across the six: **4 build in-container, 2 add a single native
config file, 0 archive a checkout.**

The nearest precedent is **`acp.py:925-966`**, which does the same job from the
*remote*: fetch into a host temp dir, verify the resolved SHA against the pinned
ref (`"Fetched ACP source commit does not match the pinned ref"`), strip `.git`,
and cap the source at `_MAX_SOURCE_FILES = 10_000`, `_MAX_SOURCE_BYTES = 100 MiB`,
`_MAX_MANIFEST_BYTES = 64 KiB`. `OmpAgent` archives `HEAD` of a caller-named path
with no manifest and no cap.

**3. `CliFlag` / `EnvVar` are legacy and unused.** No installed agent declares
either; the convention is an `options_model` subclassing
`InstalledAgentOptions`. Any plan that says "declare a `CliFlag`" is aimed at a
surface the reference agents do not use.

## The question to settle first

**Why does `OmpAgent` ship a directory at all?** Three shapes have precedent:

| shape | precedent | what it means for us |
|---|---|---|
| **build in-container from options** | `pi.py:212-343`, `hermes`, `opencode`, `gemini_cli` (4 of 6) | omp's config is generated from options; `~/.omp` never travels |
| **one native config file** | `claude_code.py:377-397`, `codex.py:1536-1569` (2 of 6) | declare `native_config=True`, `config_source` names a file or inline dict |
| **resolve a ref on the host** | `acp.py:925-966` (1 of 39) | clone/verify/validate, then upload — the *only* remote-ref precedent |

`OmpAgent` currently does a fourth thing: archive a local tree. Decide which of
the three omp should follow, **then** the ref work is a detail of the chosen
shape rather than a design in itself.

## Next steps (ordered, each with its acceptance check)

1. **Read the two docs, then choose a shape** and record it in `docs/design.md`
   with the reason and the precedent cited. *Done when:* the shape and its
   precedent are named in `docs/design.md`.
2. **Resolve the `config_source` collision** — either declare `native_config` and
   use Harbor's mechanism as `claude_code`/`codex` do, or rename the option so it
   stops shadowing. *Done when:* `grep -n config_source` shows no name shared
   with Harbor's property, or the capability is declared and the mechanism is live.
3. **Implement the chosen shape** for supplying config by ref. *Done when:* a
   trial's source record names the `omp-home` commit that was asked for.
4. **Prove the failure path.** *Done when:* a bad ref aborts at install with a
   named error, before any container command and before any model spend.
5. **Declare the API key** per whichever convention is chosen — static
   `api_key_envs` (claude_code, gemini_cli) or derived `_api_key_env_name(access)`
   (pi.py:200). *Done when:* the choice is recorded with its precedent.
6. **Gates + docs.** *Done when:* ruff, mypy, import-linter and pytest pass, and
   `docs/design.md` / `docs/spec.md` match the shipped behaviour.

## Key file paths

| path | why |
|---|---|
| `docs/established-patterns.md` | the survey — read the convention index first |
| `docs/agent-comparison.md` | the six-way comparison |
| `src/harbor_omp/omp_agent.py:224` | `class OmpAgent(BaseInstalledAgent)` |
| `src/harbor_omp/omp_agent.py:98-181` | `archive_git_head` — the unprecedented mechanism |
| `src/harbor_omp/omp_agent.py:289` | `install()` — already aborts early on an unpinnable source |
| `src/harbor_omp/omp_agent.py:364` | `_ship_config()` — ships a directory |
| `src/harbor_omp/omp_agent.py:548-563` | the in-container extract |
| `src/harbor_omp/options.py:159` | the `config_source` option that shadows Harbor's |
| `src/harbor_omp/install.py` | install commands, `SYSTEM_DEPENDENCIES`, version probe |
| `.venv/…/harbor/agents/installed/base.py:620` | the `native_config` gate |
| `.venv/…/harbor/agents/installed/acp.py:925-966` | the host-ref precedent |
| `.venv/…/harbor/agents/installed/pi.py:212-353` | build-in-container, the nearest relative |
| `docs/spec.md`, `docs/design.md`, `docs/architecture.md` | contracts to update |
| `scripts/capability_smoke.sh`, `scripts/container_smoke.py` | smoke harness |

## Decisions made and constraints discovered

- **No new CLI flag.** The convention is an options model; `CliFlag`/`EnvVar` are
  legacy. A private `--profile` would be the same false abstraction as the
  `checks.py` and `profile.py` deleted from `harness-evals`.
- **No container image.** GHCR storage and bandwidth are free for private
  packages too, so publishing buys ~$0, while an image adds either a registry
  token in the sandbox or full exposure of the content.
- **Secrets are a declared surface.** `_collect_launch_job_secrets` (Harbor's
  `cli/hosted_jobs.py`) turns every `--env-file` key into a job-scoped
  credential: encrypted, injected per trial, revoked at job end, names only.
  A private `omp-home` plus a token in `--env-file` is clean, not a loose secret.
- **Measured, not assumed:** 650 of the 651 copied files are tracked in
  `omp-home`; the exception is `agent/agents/task.md`, the seed `harness-evals`
  renders.
- **Branch naming:** this repo's guard rejects `handoff/…`; use the Linear kind
  prefix (`feature/solo-265-…`). The handoff skill's naming is overridden here.

## Open questions / risks

- **Which config-delivery shape** — the load-bearing one. Steps 1-3 depend on it.
- **Public `omp-home`, or a token in `--env-file`?** A strategy call, not a
  technical one; the secret mechanism is clean either way.
- **Does `archive_git_head` record `harness-evals`' HEAD** when the source is a
  copy inside that repo? If the trials recorded that, the recorded commit is not
  the content's provenance — a defect in its own right.
- **`OmpAgent` is the only agent that refuses to run unpinned** (35 of 39 leave
  `version=None`). Whether that should extend to the config ref is a design
  choice, not an inherited convention.
- **No `ACPAgentMixin`** — 4 of 6 mix it in; `pi` and `hermes` do not, and
  `OmpAgent` sits with them. Fine unless omp speaks ACP.

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
directory is populated. No backfill, no write target, no downstream consumer,
nothing in flight.

## Explicitly not in this doc

No secrets, no absolute paths, no hostnames, no usernames, no sample rows, no
transcripts, no connection strings. Data sources are named logically.
