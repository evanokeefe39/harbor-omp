# Established patterns in Harbor's installed agents

What the ~40 pre-integrated agents that ship with Harbor actually do, so that
`OmpAgent` can follow a convention that already exists instead of inventing one.

Every factual claim carries a `file.py:line` citation. Counts come from
mechanical passes over the installed package, not from impressions. Where the
agents disagree, this doc gives the counts rather than an average.

**Headline finding, stated first.** `pi.py` is `OmpAgent`'s nearest relative
(omp is an offshoot of pi), and the two agree on almost everything except one
thing: **pi builds the agent's config inside the container from its options;
`OmpAgent` ships a config *directory* out of a host git checkout.** One agent in
the population resolves a git ref on the host — `acp.py`, which fetches from a
**remote URL** into a host temp dir and ships the tree (§6.1) — but **none**
archives a **local** checkout's committed HEAD, and none runs `git archive`.
§6 states both sides and what the population does instead.

---

## 0. Scope and method

**Source read (read-only).** The installed Harbor package, version `0.24.0`
(`.venv/Lib/site-packages/harbor/`). Citations are relative to
`harbor/agents/installed/` unless the path says otherwise:

| prefix in this doc | absolute root |
|---|---|
| `base.py`, `pi.py`, `claude_code.py`, … | `harbor/agents/installed/` |
| `agents/base.py`, `agents/options.py`, `agents/factory.py` | `harbor/agents/` |
| `cli/hosted_jobs.py`, `cli/jobs.py`, `utils/env.py` | `harbor/` |
| `models/trial/config.py` | `harbor/` |
| `src/harbor_omp/…`, `tests/…`, `scripts/…` | this repo |

Two register files (`VERIFY.md`, `AGENTS.md`) are cited by path and row label
rather than by line: a line number inside a markdown table is not a stable
anchor, and these are registers, not code.

**Population.** The directory holds **54 `.py` files**:

| kind | count | how identified |
|---|---|---|
| modules defining a `BaseInstalledAgent` subclass | 38 | `^class X(...BaseInstalledAgent...)` |
| agent classes | **39** | `cline/cline.py` holds one in a subpackage |
| `base.py` | 1 | the contract; defines no agent |
| support modules | 15 | `acp_registry.py`, `acp_runner.py`, `antigravity_base_url.py`, `antigravity_sdk_runner.py`, `cline/__init__.py`, `cline/trajectory.py`, `deerflow_runner.py`, `fx_dev.py`, `langgraph_runner.py`, `nemo_agent_run_wrapper.py`, `node_install.py`, `openhands_sdk_runner.py`, `strands_runner.py`, `strands_trajectory.py` |

38 + 1 + 15 = 54. The 39 classes: `AcpAgent`, `Aider`, `AntigravityCli`,
`AntigravitySDK`, `ClaudeCode`, `ClineCli`, `CodePuppy`, `Codex`, `CopilotCli`,
`CortexCode`, `CursorCli`, `DeerFlow`, `Devin`, `Eve`, `Fx`, `GeminiCli`,
`Goose`, `GrokBuild`, `Hermes`, `Junie`, `KimiCli`, `KimiCode`, `LangGraph`,
`MCode`, `MiMo`, `MiniSweAgent`, `MuseCode`, `NemoAgent`, `OpenClaw`,
`OpenCode`, `OpenHands`, `OpenHandsSDK`, `Pi`, `QwenCode`, `RovodevCli`,
`Strands`, `SweAgent`, `TraeAgent`, `Vibe`.

**Method.** `base.py` and `agents/base.py` were read in full. Read in detail:
`pi.py` (the primary reference — constants, options, install, the four config
builders, `run`, `populate_context_post_run`, `_load_trajectory`),
`claude_code.py`, `aider.py`, `acp.py`, `cline/cline.py`, `codex.py`,
`cursor_cli.py`, `deerflow.py`, `goose.py`, `junie.py`, `mini_swe_agent.py`,
`openhands.py`, `swe_agent.py`. The other 26 were mechanically extracted —
`capabilities`, `MODEL_CONNECTION`, `Cli`/`Env` annotation counts, the
`get_version_command`/`parse_version` bodies, the install-command strings, and
the config/upload call sites — which is what the counts rest on. Nothing is
asserted about an agent whose relevant text was not read.

**Where the parent brief's anchors were off.** Three named symbols do not exist
as described; this doc uses the real ones:

- `swe_agent._build_clone_command(repo_url, destination, version)` is
  `_build_swe_agent_clone_command(version, *, repo_url=…, destination=…)` at
  `swe_agent.py:36` (the brief's `:42` is the docstring's last line).
- `SYSTEM_DEPENDENCIES` is **not** a Harbor base-class symbol. The base class has
  `SYSTEM_PACKAGES` (`base.py:363`); `SYSTEM_DEPENDENCIES` is this repo's own
  tuple (`src/harbor_omp/install.py:26`).
- `base.py:1067 abstract install()` — `install` is at `base.py:1068`, with
  `@abstractmethod` at `base.py:1067`.

### Convention index

| # | convention | section |
|---|---|---|
| C1 | implement `name`/`install`; never `resume`/`load`/`preflight`/`config_source` | 1 |
| C2 | declare `options_model` and `capabilities` | 1, 2 |
| C3 | declare flags with `Cli(...)`/`Env(...)` on the options model, never `CLI_FLAGS`/`ENV_VARS` | 2 |
| C4 | the option names *are* the contract (`--ak name=value`) | 2 |
| C5 | declare credentials as `MODEL_CONNECTION` | 2, 7 |
| C6 | build config in the container from options | 3, 6 |
| C7 | `ensure_system_dependencies` with named packages; never override `SYSTEM_PACKAGES` | 4 |
| C8 | install as the agent user, system packages as root | 4 |
| C9 | `set -euo pipefail`, and print the version at the end of install | 4, 5 |
| C10 | a re-install is a no-op when the CLI is already there | 4 |
| C11 | pin with `version`; report with `get_version_command` + `parse_version` | 5 |
| C12 | a measured version is not a claimed one | 5 |
| C13 | clone at a ref with an explicit resolution order | 6 |
| C14 | secrets arrive as env vars; keys are never written to disk | 7 |
| C15 | only secret *names* are displayed | 7 |
| C16 | refuse before spending: validate, then upload, then run | 8 |
| C17 | name the failure with a typed error so retry policy can target it | 8 |
| C18 | fail open on classification | 8 |
| C19 | unit tests drive the agent's own commands through a recording environment | 9 |
| C20 | a container smoke, not CI, proves the recipes on real Linux | 9 |
| C21 | a no-op run is reported as failed, not scored | 8 |
| C22 | reset the agent's config home; never inherit image content | 4 |
| C23 | record provenance (argv, commit, source) in the log dir | 6 |
| C24 | declare only the capabilities whose behaviour exists | 2 |
| C25 | a config file the agent must reference *symbolically* needs the key's env **name**, derived — not a static list | 7 |

---

## 1. The class contract

### 1.1 What Harbor requires

`BaseAgent` (`agents/base.py:29`) is the ABC. Three abstract members:

| member | line |
|---|---|
| `name()` | `agents/base.py:327` (`@staticmethod @abstractmethod`) |
| `version()` | `agents/base.py:331` |
| `setup(environment)` | `agents/base.py:342` |
| `run(instruction, environment, context)` | `agents/base.py:358` |

`BaseInstalledAgent` (`base.py:346`) adds one abstract member — `install`
(`base.py:1068`) — and **supplies** `setup` (`base.py:1077`), so a concrete agent
overrides only `install`. `setup` creates `/installed-agent` as root
(`base.py:1079`), makes `<logs_dir>/setup` (`base.py:1083`), calls `install` and
wraps any non-`RuntimeError` exception as `RuntimeError("Agent install
failed: …")` (`base.py:1091`), then probes the version when the caller pinned
nothing (`base.py:1093-1101`).

**C1.** All 39 define `name` and `install`. 38 of 39 inherit `version()` from
`base.py:870`; only `goose.py:113` and `hermes.py:105` override it, to substitute
a readable default (`goose.py:114` returns `self._version or "stable"`).

### 1.2 The optional hooks

| hook | base line | overridden by | who |
|---|---|---|---|
| `install` | `base.py:1068` (abstract) | 39/39 | every agent |
| `populate_context_post_run` | `agents/base.py:411` | 35/39 | all but `deerflow.py`, `fx.py`, `kimi_code.py`, `langgraph.py` |
| `get_version_command` | `base.py:873` | 38/39 | all but `acp.py` (it takes its version from a registry entry, `acp.py:498`, or a manifest, `acp.py:1094`) |
| `parse_version` | `base.py:878` | 19/39 | only where the CLI's output needs parsing |
| `config_source` (property) | `base.py:685` | **0/39** | nobody overrides it; 5 agents read it |
| `remote_session_logs_dir` | `base.py:352` | 2/39 | `claude_code.py:602`, `codex.py:569` |
| `convert_trajectory` | `base.py:356` | 2/39 | `claude_code.py:606`, `codex.py:573` |
| `handoff` | `agents/base.py:404` | 2/39 | `claude_code.py:202`, `muse_code.py:440` |
| `resume` | `base.py:1155` | **0/39** | base gates on `capabilities.resume` |
| `load` | `base.py:1170` | **0/39** | base gates on `capabilities.load_*` |
| `preflight` | `agents/base.py:222` | **0/39** | base validates options; nobody adds to it |
| `_validate_native_load_trajectory` | `base.py:1138` | the 3 with load support | `claude_code.py:179`, `codex.py:156`, `muse_code.py:301` |
| `DEFAULT_SETUP_TIMEOUT_SEC` | `agents/base.py:59` | 1/39 | `hermes.py:97` sets 1200.0, with the measured reason at `hermes.py:94-96` |

The 39 never override `resume`, `load`, `preflight` or `config_source`. Those are
driven by `capabilities` and by base machinery:

- `resume` sets a transient class flag `_resume` (`base.py:1106`) and calls
  `run()` (`base.py:1155`); the agent's command builder reads `self._resume`
  (`pi.py:429`).
- `load` sets `_load` (`base.py:1112`) and calls `run()` (`base.py:1170`);
  `_seed_load_trajectory` (`base.py:1192`) uploads the session first.
- `config_source` is a base property returning a deep copy of the constructor's
  `config` (`base.py:685-687`).

### 1.3 Capability declaration

`capabilities` is a frozen pydantic model (`capabilities.py:8`), declared as a
`ClassVar` on `BaseAgent` (`agents/base.py:56`) and checked in
`__init_subclass__` (`agents/base.py:88-92`). Fields: `atif`
(`capabilities.py:13`), `resume` (`:17`), `load_native_trajectory` (`:21`),
`load_atif_trajectory` (`:25`), `handoff` (`:29`), `native_config` (`:33`),
`windows` (`:37`), `skills` (`:41`), `mcp_servers` (`:46`), `bridges` (`:51`).

Deprecated aliases (`SUPPORTS_ATIF` … `SUPPORTED_BRIDGES`, `agents/base.py:64-71`)
are translated by `_LEGACY_CAPABILITY_FIELDS` (`agents/base.py:75-84`), warn
(`agents/base.py:123-129`) and conflict-check (`agents/base.py:104-114`). **No
installed agent uses them**; all 39 declare `capabilities` directly.

---

## 2. The declarative surfaces

### 2.1 `CliFlag` and `EnvVar` are legacy and unused

`CliFlag` (`base.py:191-205`) and `EnvVar` (`base.py:208-219`) map a kwarg to a
flag or env var:

| `CliFlag` | line | `EnvVar` | line |
|---|---|---|---|
| `kwarg` | `base.py:199` | `kwarg` | `base.py:212` |
| `cli` | `base.py:200` | `env` | `base.py:213` |
| `type` | `base.py:201` | `type` | `base.py:214` |
| `choices` | `base.py:202` | `choices` | `base.py:215` |
| `default` | `base.py:203` | `default` | `base.py:216` |
| `env_fallback` | `base.py:204` | `env_fallback` | `base.py:217` |
| `format` | `base.py:205` | `bool_true` / `bool_false` | `base.py:218-219` |

**`CLI_FLAGS` is declared by 0 of 39; `ENV_VARS` by 0 of 39.** The class
attributes default to empty lists (`base.py:360-361`), and `__init_subclass__`
refuses a class that sets both an `options_model` and either legacy list
(`base.py:585-592`). `agents/options.py:1-6` states the intent: they "stay on
`BaseInstalledAgent` for backwards compatibility".

### 2.2 `options_model` is the convention

**39 of 39 declare `options_model`.** 37 declare a subclass of
`InstalledAgentOptions`; 2 use it directly (`devin.py:56`, `kimi_code.py:45`).
`InstalledAgentOptions` (`agents/options.py:56-70`) contributes three fields:

| field | line | meaning |
|---|---|---|
| `version` | `agents/options.py:59` | "Agent CLI version to install. Omit for latest." |
| `prompt_template_path` | `agents/options.py:63` | Jinja2 template; must include `{{ instruction }}` |
| `config` | `agents/options.py:67` | native config file path or inline JSON |

`AgentOptions` sets `extra="forbid"` (`agents/options.py:53`), so an unknown
`--ak` name is a hard error, rendered as an "Unknown option 'x'" list pointing
at the schema (`agents/base.py:196-218`).

### 2.3 Flags and env vars are annotations on the model

`Cli` (`agents/options.py:16`, signature `18-29`) and `Env`
(`agents/options.py:33`, signature `34-42`) are `Annotated` metadata:

```python
max_turns: Annotated[int | None, Cli("--max-turns", fallback="CLAUDE_CODE_MAX_TURNS")]
```

`pi.py:73-76` is the nearest analogue for `OmpAgent`'s `--thinking`:

```python
thinking: Annotated[
    Literal["off", "minimal", "low", "medium", "high", "xhigh", "max"] | None,
    Cli("--thinking"),
] = Field(default=None, validation_alias=AliasChoices("thinking", "reasoning_effort"), ...)
```

**Counts:** `Cli(` in **23 of 39**; `Env(` in **6 of 39** (`claude_code.py`,
`fx.py`, `goose.py`, `nemo_agent.py`, `openhands.py`, `qwen_code.py`).
`openhands.py` uses 10 `Env(` and no `Cli(`; `claude_code.py` uses 9 `Cli(` and 1
`Env(`. The split follows whether the CLI takes a flag or an env var.

Three refinements, each rare:

- `format=` — 7 agents (`claude_code.py`, `codex.py`, `copilot_cli.py`,
  `cursor_cli.py`, `mcode.py`, `mimo.py`, `opencode.py`).
- `fallback=` — the env-var name a flag falls back to; applied by
  `apply_env_fallbacks` (`agents/options.py:73-99`) *before* validation.
- `sensitive=True` — **1 agent**: `swe_agent.py:254`; masked by `_redact_command`
  (`base.py:898-910`) via `sensitive_option_values` (`agents/options.py:135`).

`AliasChoices` is the convention for a renamed option: `pi.py:78` accepts
`thinking` or `reasoning_effort`, and this repo does the same
(`src/harbor_omp/options.py:135`).

### 2.4 `api_key_envs` and `capabilities` — real counts

| surface | count of 39 | who |
|---|---|---|
| declares `MODEL_CONNECTION` | 18 | §7 |
| `api_key_envs=(...)` inside that spec | 7 | `claude_code.py:126`, `code_puppy.py:115`, `fx.py:53`, `gemini_cli.py:95`, `mini_swe_agent.py:509`, `muse_code.py:77`, `openhands.py:106` |
| overrides the `model_connection` property | 11 | `aider.py`, `claude_code.py`, `gemini_cli.py`, `goose.py`, `mimo.py`, `mini_swe_agent.py`, `muse_code.py`, `opencode.py`, `openhands.py`, `strands.py`, `trae_agent.py` |
| declares `capabilities` | 39 | — |
| …`atif=True` | 32 | |
| …`mcp_servers=True` | 31 | |
| …`skills=True` | 24 | |
| …`resume=True` | 17 | |
| …`native_config=True` | 5 | `claude_code.py:119`, `codex.py:127`, `deerflow.py:156`, `junie.py:352`, `muse_code.py:72` |
| …`load_native_trajectory=True` | 3 | `claude_code.py`, `codex.py`, `muse_code.py` |
| …`load_atif_trajectory=True` | 3 | same three |
| …`handoff=True` | 2 | `claude_code.py:118`, `muse_code.py` |
| …`bridges=` | 4 | `claude_code.py`, `codex.py`, `gemini_cli.py`, `opencode.py` — all `frozenset({BridgeKind.ACP})` |
| …`windows=True` | **0** | — |
| empty `AgentCapabilities()` | 1 | `code_puppy.py:107` |

**C24.** `native_config=True` and reading `self.config_source` are the same five
agents (`claude_code.py:379`, `codex.py:1538`, `deerflow.py:463`,
`junie.py:451`, `muse_code.py:95`). `OmpAgent` states the rule in its own
docstring (`src/harbor_omp/omp_agent.py:238-240`), and this repo encodes it as a
check (`VERIFY.md`, row `tests/test_package.py`).

---

## 3. The primary reference: `pi.py`

omp is an offshoot of pi, so `pi.py` (1065 lines) is the comparison that matters
most. The two agree on the shape and differ on where config comes from.

### 3.1 `pi.py` structure, verified

| member | line |
|---|---|
| `_CURRENT_PI_PACKAGE` / `_LEGACY_PI_PACKAGE` / rename at `0.74.0` | `pi.py:42-44` |
| `_PI_CONFIG_DIR_ENV = "PI_CODING_AGENT_DIR"` | `pi.py:46` |
| `_REMOTE_PI_CONFIG_DIR = /tmp/harbor-pi-agent` | `pi.py:47` |
| `_MODELS_FILENAME` / `_MCP_CONFIG_FILENAME` / `_MAX_TURNS_EXTENSION_FILENAME` | `pi.py:48-50` |
| MCP adapter pin (`pi-mcp-adapter@2.34.0`, pi range) | `pi.py:53-58` |
| `PiOptions(InstalledAgentOptions)` | `pi.py:72` |
| `class Pi(BaseInstalledAgent)` | `pi.py:91` |
| `capabilities = AgentCapabilities(atif, resume, skills, mcp_servers)` | `pi.py:92-97` |
| `MODEL_CONNECTION = ModelConnectionSpec(passthrough=True)` | `pi.py:98` |
| `options_model = PiOptions` | `pi.py:104-105` |
| `name()` / `get_version_command()` / `parse_version()` | `pi.py:120` / `124` / `128` |
| `_package_name()` — legacy package below `0.74.0` | `pi.py:131` |
| `install()` | `pi.py:141` |
| `_api_key_env_name(access)` | `pi.py:200` |
| `_build_custom_models_json` / `_write_custom_models_json` | `pi.py:212` / `252` |
| `_ensure_config_dir` | `pi.py:270` |
| `_build_mcp_config` / `_write_mcp_config` | `pi.py:277` / `299` |
| `_build_max_turns_extension` / `_write_max_turns_extension` | `pi.py:310` / `328` |
| `_build_register_skills_command` | `pi.py:345` |
| `run()` | `pi.py:377` |
| `populate_context_post_run()` | `pi.py:460` |
| `_load_trajectory` / `_accounting_metrics` / `_metrics_from_usage` / `_sum_metrics` | `pi.py:501` / `538` / `668` / `712` |
| `_convert_session_events_to_trajectory` / `_populate_context_from_output` | `pi.py:733` / `1030` |

### 3.2 `pi` vs `omp`, concern by concern

| concern | `pi.py` | `OmpAgent` |
|---|---|---|
| options model | `PiOptions` (`pi.py:72`), 1 `Cli(` annotation (`pi.py:74`) | `OmpOptions` (`src/harbor_omp/omp_agent.py:253`), 0 `Cli(`; flags travel as a verbatim `run_flags` list (`src/harbor_omp/options.py:138`) |
| model connection | `passthrough=True` (`pi.py:98`) | `passthrough=True` (`src/harbor_omp/omp_agent.py:251`) — identical |
| install | nvm + `npm install -g --ignore-scripts {pkg}{version}` (`pi.py:193`) | bun + `bun install -g --ignore-scripts {spec}` (`src/harbor_omp/install.py:63`) — same `--ignore-scripts` discipline |
| system deps | `("curl",)` (`pi.py:178`) | `("curl", "git", "unzip")` (`src/harbor_omp/install.py:26`, used at `src/harbor_omp/omp_agent.py:301`) |
| version probe | `. ~/.nvm/nvm.sh; pi --version` (`pi.py:125`), last line (`pi.py:129`) | `install.version_command()` → `omp --version`, last line (`src/harbor_omp/install.py:71-81`) |
| isolated config home | `PI_CODING_AGENT_DIR=/tmp/harbor-pi-agent` (`pi.py:409`) | `HOME=<config_home> PI_CONFIG_DIR=.omp` (`src/harbor_omp/omp_agent.py:492`, `:624`) |
| **config content** | **built in the container from options** — models.json (`pi.py:212-267`), mcp.json (`pi.py:299-307`), `max-turns.ts` (`pi.py:328-343`) | **built in the container** for skills/MCP (`src/harbor_omp/omp_agent.py:481-545`) **plus a shipped directory from a host git checkout** (`src/harbor_omp/omp_agent.py:364-402`) |
| skills | `cp -r {skills_dir}/* $HOME/.agents/skills/` (`pi.py:345-353`) | `cp -r {skills_dir}/* <config_dir>/agent/skills/` (`src/harbor_omp/omp_agent.py:516-521`) |
| MCP | `_upload_config_text` → `<config_dir>/mcp.json` (`pi.py:299-307`) | `echo {json} > <config_dir>/agent/mcp.json` inside the strict script (`src/harbor_omp/omp_agent.py:525-543`) |
| extension point | a TypeScript extension written to disk and passed as `--extension` (`pi.py:328`, `:420-422`) | `run_flags` (`--no-extensions` in the default recipe, `src/harbor_omp/options.py:30-35`) plus an installed plugin (`omp install` / `omp plugin enable`, `src/harbor_omp/omp_agent.py:507-514`) |
| file permissions on generated config | `chmod 600` on models.json (`pi.py:267`), `chmod 700` on the config dir (`pi.py:274`) | no permission step; the config dir is created inside the strict script (`src/harbor_omp/omp_agent.py:481-495`) |
| key reference in config | symbolic: `"apiKey": f"${api_key_env}"` (`pi.py:245`), name derived (`pi.py:200`) | by value: `env=dict(self.model_connection.env)` on the exec (`src/harbor_omp/omp_agent.py:589`) |
| run | `pi --print --mode json --session-dir … {extensions} {cli_flags} {instruction}`, piped through `tee` (`pi.py:441-455`) | argv built in `_run_argv` (`src/harbor_omp/omp_agent.py:736`), recorded to `run-flags.json` before launch (`src/harbor_omp/omp_agent.py:579`) |
| post-run | reads the newest session JSONL, writes `trajectory.json`, sums metrics (`pi.py:460-497`) | sums the session dir, writes the ATIF trajectory last (`src/harbor_omp/omp_agent.py:770-846`) |
| resume | `--continue` when `self._resume` (`pi.py:429`) | `--resume <stem>` from the loaded session (`src/harbor_omp/omp_agent.py:761-762`) |

**Read this table as: the two agree on identity, install, version, isolation,
skills, MCP and post-run accounting, and differ on exactly one axis — where the
config content comes from (§6), and consequently on the file-permission step and
on whether a key is referenced symbolically.**

### 3.3 `_api_key_env_name`: a shared pattern, not a pi quirk

The parent's question was whether deriving the key env name from the resolved
connection is pi-only. It is not. **7 of 39** derive a key env name rather than
declaring a static tuple:

| agent | mechanism | line |
|---|---|---|
| `pi.py` | scans `access.env` for the entry whose value equals `access.api_key` | `pi.py:200-210`, used at `pi.py:227` |
| `mcode.py` | `provider_access.api_key_envs` ∩ `env` | `mcode.py:164-170`, used at `mcode.py:382` |
| `cline/cline.py` | a `PROVIDER_API_KEY_ENVS` provider→env map | `cline/cline.py:191`, used at `cline/cline.py:732` |
| `nemo_agent.py` | a per-provider spec record carrying `api_key_env` | `nemo_agent.py:95`, `:106`, `:111` |
| `deerflow.py` | returns `(use, model_id, base_url, api_key_env_var)` | `deerflow.py:244` |
| `code_puppy.py` | maps a native model type to an `api_key_env` | `code_puppy.py:205-206` |
| `vibe.py` | derives the env name for its config | `vibe.py:237`, `:317`, `:320` |

**C25 — the rule behind it.** You need the *name* only when the config must
reference the key **symbolically** rather than pass it **by value**. `pi.py` is
the only agent that writes `"apiKey": "$VAR"` (`pi.py:245`, count: 1 of 39),
because its `models.json` is read by pi itself and pi resolves `$VAR` from its
own environment. The 14 agents that pass the resolved env through by value
(`access.env` / `model_connection.env` — `aider.py:126`, `fx.py:226`,
`goose.py:761`, `mini_swe_agent.py:526`, `openhands.py:920`, `pi.py:391`,
`swe_agent.py:536`, `trae_agent.py:214` and others) never need the name at all.
`OmpAgent` is in the by-value camp (`src/harbor_omp/omp_agent.py:589`), so it
needs no derivation — **unless** the eval-config-from-git-ref design puts a key
reference into shipped config content, in which case `pi.py:200` is the pattern
to copy, not a static `api_key_envs` tuple.

---

## 4. Install conventions

### 4.1 The styles observed

`install()` is the one method every agent writes (`base.py:1068`). Six styles,
sometimes combined:

| style | example | citation |
|---|---|---|
| npm global | `npm install -g @openai/codex{version_spec}` | `codex.py:432` |
| npm global, musl branch | `npm install -g @anthropic-ai/claude-code` | `claude_code.py:483` |
| npm with `--ignore-scripts` | `npm install -g --ignore-scripts {package_name}{version_spec}` | `pi.py:193` |
| vendor `curl \| bash` installer | `curl -LsSf https://aider.chat/install.sh \| sh` | `aider.py:91` |
| release-artifact script | `curl -fsSL …/releases/download/{version}/download_cli.sh \| bash` | `goose.py:172` |
| uv tool / uv pip / venv | `uv tool install --python 3.13 kimi-cli{version_spec}` | `kimi_cli.py:189` |
| uv pip into a venv, from source | `uv pip install /opt/sweagent-repo` | `swe_agent.py:426` |
| git clone + build | `git clone --depth 1 <repo> <dir>` | `deerflow.py:578` |
| distro package manager | `apt-get install -y curl ca-certificates git unzip` | `cline/cline.py:826` |
| verified source checkout | `uv sync --frozen --project …` | `acp.py:1136-1142` |

`acp.py` is the outlier with a deliberate two-mode install: a pinned source
checkout when one is configured (`acp.py:1167-1170`), otherwise a
registry-selected distribution — `npx` or `binary` — chosen from the detected
platform (`acp.py:1172-1190`).

### 4.2 System dependencies

`SYSTEM_PACKAGES` (`base.py:363-486`) is a dict of named `PackageSpec`
(`base.py:325-344`) covering curl, bash, git, build tools, tmux, ripgrep, xz,
ca-certificates, procps, coreutils, bzip2, tar, unzip, wget, gnupg, python3,
python3-pip, python3-venv, nodejs, npm, libxcb and libgomp — each with the
per-manager name for apt-get/dnf/yum/apk.

`ensure_system_dependencies(environment, ("curl", "git"))` (`base.py:723`)
validates the names against `SYSTEM_PACKAGES` (`base.py:731`), skips anything
whose probe command is already present unless `always_install` is set
(`base.py:740`), then installs the union through whichever manager exists
(`base.py:706-721`, `base.py:754-786`).

**36 of 39 call it.** The three that do not — `acp.py`, `cline/cline.py`,
`kimi_code.py` — do their own package work (`cline/cline.py:815-830`,
`kimi_code.py:65-92`). **`SYSTEM_PACKAGES` is overridden by 0 of 39**: an agent
that needs a package adds its name to the call.

Most common tuples: `("curl",)` ×8, `("curl", "bash")` ×3, `("curl", "git")` ×2,
`("curl", "coreutils")` ×2. Others in use: `("curl", "bash", "git")`
(`copilot_cli.py:88`), `("curl", "bash", "unzip")` (`junie.py:413`),
`("curl", "build_tools", "git", "tmux", "coreutils")` (`swe_agent.py:400`),
`("curl", "git", "ripgrep", "xz")` (`hermes.py:114`),
`("curl", "bzip2", "libxcb", "libgomp")` (`goose.py:130`),
`("wget", "gnupg", "git")` (`rovodev_cli.py`),
`("curl", "git", "build_tools", "tmux")` (`openhands.py:849`),
`("ca_certificates",)` (`antigravity_cli.py:292`); `nemo_agent.py:221` passes a
computed tuple.

### 4.3 Root vs agent user

`exec_as_root` (`base.py:1010`) is for system packages, symlinks and ownership;
`exec_as_agent` (`base.py:1023`) for user-level installs. Both wrap `_exec`
(`base.py:950`), which prefixes `set -o pipefail` (`base.py:984`), truncates
output head-and-tail (`base.py:883-896`) and raises the classified error on a
non-zero exit (`base.py:999`).

19 of 39 call `exec_as_root`. The split is visible inside one install:
`openhands.py:856` creates and `chown`s `/opt/openhands-venv` as root, then
installs into it as the agent user (`openhands.py:867-882`); `codex.py:445-458`
symlinks the binaries into `/usr/local/bin` as root after installing as the
agent. `pi.py:188-196` installs wholly as the agent user.

`set -euo pipefail` appears in 34 of 39 install commands. This repo states the
reason: "a failed install fails the trial at setup, before any model spend"
(`src/harbor_omp/install.py:8-13`).

### 4.4 Idempotency

Three agents probe before the expensive work and skip when satisfied:
`claude_code.py:466-473` (via `_installed_claude_satisfies_version`,
`claude_code.py:451-463`), `codex.py:417-423` (via
`_installed_codex_satisfies_version`, `codex.py:403-414`), and
`deerflow.py:534-542` (via `_INSTALL_CHECK_COMMAND`, `deerflow.py:124`), which
rewrites the config either way (`deerflow.py:542`).

### 4.5 The config home

The agents that need isolation reset it. `OmpAgent` resets the home and lands
the seed, the shipped config and the plugin in a fixed order
(`src/harbor_omp/omp_agent.py:436-449`, command at `:481`), and
`deerflow.py:542` rewrites its `config.yaml` on every trial — "Runs on every
trial, covering the idempotent path where `_install_harness` is skipped"
(`deerflow.py:593`).
`pi.py` creates `/tmp/harbor-pi-agent` `chmod 700` (`pi.py:270-275`) and points
pi at it with `PI_CODING_AGENT_DIR` (`pi.py:409`) — the same shape as omp's
`PI_CONFIG_DIR` (`src/harbor_omp/omp_agent.py:492`).

---

## 5. Version pinning and reporting

### 5.1 The split

| | what it is | where it lives |
|---|---|---|
| **the pin** | what the install installs | `options.version` (`agents/options.py:59`) |
| **the report** | what the container measured | `self._version` after `setup()` probes it (`base.py:1093-1101`) |

`setup` probes only when nothing was pinned, calls `get_version_command()`
(`base.py:873`) and parses with `parse_version()` (`base.py:878`); the block is
wrapped so "Version detection is best-effort" (`base.py:1101`). `version()`
returns `self._version` (`base.py:870`), and `to_agent_info` renders it as
`self.version() or "unknown"` (`agents/base.py:306-321`).

### 5.2 How agents pin

The default is unpinned. Every install builds its spec conditionally:
`version_spec = f"@{self._version}" if self._version else "@latest"`
(`codex.py:426`, `gemini_cli.py:172`, `kimi_code.py:90`, `mcode.py:123`,
`openclaw.py:533`, `opencode.py:137`), `f"=={self._version}"` for pip/uv
(`code_puppy.py:150`, `kimi_cli.py:182`, `mini_swe_agent.py:642`), or a version
flag spliced into the installer (`devin.py:126`, `grok_build.py:389`,
`junie.py:419`). `pi.py:142-176` goes further: it validates the pinned version
against the MCP adapter's supported range (`pi.py:54-56`) and the max-turns
minimum (`pi.py:56`), raising `ValueError` with the required range.

Agents that pin by default do it through an option default or a constant:
`deerflow.py:33` (`_DEERFLOW_REF`, reason at `deerflow.py:30-32`),
`claude_code.py:151` (`CLAUDE_CODE_ACP_VERSION = "0.16.2"`),
`openhands.py:89` (`python_version`).

`OmpAgent` is the only agent in either population that refuses to run unpinned:
`version` defaults to `PINNED_OMP_VERSION` (`src/harbor_omp/options.py:23`) and a
`field_validator` converts `None` into it (`src/harbor_omp/options.py:67-75`),
because `BaseInstalledAgent.__init__` always forwards `version=None`
(`src/harbor_omp/options.py:68-74`).

### 5.3 Why a measured version is not a claimed one

- **`OmpAgent` discards the pin from the reported version.** `__init__` sets
  `self._version = None` after `super().__init__`
  (`src/harbor_omp/omp_agent.py:265`), so `setup` probes the CLI that actually
  landed; the comment says Harbor would otherwise read `options.version` as the
  reported version and never probe (`src/harbor_omp/omp_agent.py:260-264`). The
  pin still governs the install and is recorded in `run-flags.json`
  (`src/harbor_omp/omp_agent.py:79`).
- **`hermes.py` keeps a separate flag for "was it pinned".**
  `self._version_was_pinned = version is not None` (`hermes.py:82`), captured
  before `super().__init__`, because "BaseInstalledAgent.setup fills _version
  after installation, so _version alone cannot tell us whether the user selected
  an older Hermes release" (`hermes.py:80-81`); read at `hermes.py:509`.

The same discipline shows in the install command: most agents print the version
as the last step (`claude_code.py:489`, `codex.py:441`, `goose.py:174`,
`junie.py:428`, `kimi_cli.py:190`, `openhands.py:876`, `pi.py:195`), so the
install is its own first evidence.

### 5.4 `parse_version` shapes

19 of 39 parse. Four recurring shapes:

| shape | example |
|---|---|
| last non-empty line | `code_puppy.py:141-144`, `kimi_code.py:57-62`, `junie.py:404-408`, `pi.py:129` |
| regex for `\d+\.\d+\.\d+` | `copilot_cli.py:79-82` (`_RE_VERSION`, `copilot_cli.py:65`), `cortex_code.py:686-689`, `goose.py:121-125`, `muse_code.py:131-133` |
| strip a `Version:` prefix | `antigravity_sdk.py:110-113`, `swe_agent.py:300-303` |
| no parsing needed | `openhands_sdk.py:123` (`stdout.strip()`) |

`OmpAgent` delegates both to this repo's `install` module
(`src/harbor_omp/omp_agent.py:278-286` → `src/harbor_omp/install.py:71-81`),
whose `parse_version` takes the last non-empty line for the same reason
`junie.py:405` does.

---

## 6. Supplying content from a git repo — and the config-directory question

This is the section the design under review turns on, so it answers one question
first and then gives the surrounding conventions.

### 6.1 The question, answered

> **Is shipping a config *directory* out of a host git checkout a convention any
> installed agent follows?**

**Partly — and the distinction matters.** Resolving a git ref on the host and
shipping the resulting tree **has one precedent, `acp.py`**. Archiving a
**local** checkout's committed HEAD has **none**.

| pattern | count of 39 | evidence |
|---|---|---|
| resolves a git ref on the **host** and ships the tree | **1** | `acp.py:925-966` (via `_run_git`, `acp.py:848`) |
| runs `git archive` / `make_archive` on a checkout | **0** | mechanical scan for `git archive`, `archive_git`, `make_archive`: 0 files |
| ships a **local** checkout's committed HEAD | **0** | `acp.py`'s source is a remote `repo_url` + `ref` (`acp.py:930-955`), not a path |
| uploads a host **directory** into the container | 6 | `acp.py:1116`, `eve.py:513`, `langgraph.py:397`, `muse_code.py:344`, `nemo_agent.py:279`, `strands.py:384` |
| uploads a host **file** into the container | 12 | `acp.py:1149`, `codex.py:1706`, `deerflow.py:604`, `gemini_cli.py:879`, `langgraph.py:400`, `nemo_agent.py:269`, `strands.py:380`, `cline/cline.py:861`, `eve.py:517`, `antigravity_cli.py:293`, `antigravity_sdk.py:144`, `openhands_sdk.py:171` |
| consumes Harbor's native `config` channel (`native_config` + `config_source`) | 5 | §2.4 |

**The precedent: `acp.py`.** It is the only agent that resolves a ref on the host,
and it does so with considerably more machinery than `OmpAgent`:

- `_run_git` (`acp.py:848-889`) runs git as a host subprocess with `GIT_TERMINAL_PROMPT=0`
  (`acp.py:857`), `GIT_LFS_SKIP_SMUDGE=1` (`acp.py:859`), and — when a scoped
  token is used — strips ambient credential programs and config
  (`_SCOPED_GIT_ENV_VARS`, `acp.py:840-847`; the strip loop at `acp.py:863-869`),
  then sets `GIT_CONFIG_NOSYSTEM=1` and `GIT_CONFIG_GLOBAL=os.devnull`
  (`acp.py:870-871`). It raises git's own stderr into the error (`acp.py:886-888`).
- `_source_askpass_env` (`acp.py:891-923`) writes a scoped askpass script and
  refuses to authenticate anything but `https://github.com` (`acp.py:905-914`).
- `_fetch_source` (`acp.py:925-966`) does `git init` → `remote add origin` →
  `fetch --depth 1 --no-tags origin <ref>` with `protocol.file.allow=never` →
  `checkout --detach FETCH_HEAD` → `rev-parse HEAD`; it **verifies a pinned ref
  against the resolved SHA** (`acp.py:963-964`), then deletes `.git` before
  upload (`acp.py:966`).
- `_load_verified_manifest` (`acp.py:973-978`) validates a manifest and returns
  its digest, under caps of 10 000 files, 100 MiB and a 64 KiB manifest
  (`acp.py:968-970`).
- The checkout dir is a **host** temp dir (`acp.py:1078`), and the tree is then
  uploaded (`acp.py:1116`) and built with `uv sync --frozen` (`acp.py:1136-1142`).

`pi.py` — the nearest relative — is squarely on the **build-in-container** side,
and has **no `config_source` handling and no `_ship_config`**. Every config file
is generated from options and uploaded or written:

- `_build_custom_models_json` (`pi.py:212`) → `_write_custom_models_json`
  (`pi.py:252`) → `_upload_config_text` (`base.py:1036`) → `chmod 600`
  (`pi.py:267`).
- `_build_mcp_config` (`pi.py:277`) → `_write_mcp_config` (`pi.py:299`).
- `_build_max_turns_extension` (`pi.py:310`) → `_write_max_turns_extension`
  (`pi.py:328`) → passed to the CLI as `--extension` (`pi.py:420-422`).
- `_build_register_skills_command` (`pi.py:345`) copies skills with `cp -r`
  inside the container.
- `_ensure_config_dir` (`pi.py:270`) makes the dir `chmod 700`.

`OmpAgent` does the container-side half too — skills copy and MCP write
(`src/harbor_omp/omp_agent.py:516-543`) — **and** additionally ships a directory:
`_ship_config` (`src/harbor_omp/omp_agent.py:364-402`) calls `archive_git_head`
(`src/harbor_omp/omp_agent.py:98`), uploads the tar (`:397`), records the commit
(`:398-402`), and extracts it after the home reset
(`_config_extract_command`, `src/harbor_omp/omp_agent.py:548`).

### 6.2 Both sides, cited

**What `OmpAgent` gets from shipping.** The shipped content is a whole config
tree — skills, rules, agents, hooks (`src/harbor_omp/options.py:159-179`) —
where the population's mechanism is per-file: `pi.py` builds three named files
and one skills copy; `claude_code.py:107` takes a single `memory_dir`; Harbor's
native `config` is one file or one inline JSON object
(`agents/options.py:67`). A directory ship is the only way to move a tree of
arbitrary config content without enumerating it. Three precedents point the same
way: `acp.py:925-966` (resolve a ref on the host, ship the tree),
`claude_code.py:1705-1715` (a host memory directory copied into Claude's config),
and the six `upload_dir` callers (`acp.py:1116`, `eve.py:513`,
`langgraph.py:397`, `muse_code.py:344`, `nemo_agent.py:279`, `strands.py:384`).

**What it costs, in the population's terms.**

1. **The precedent fetches from the network; `OmpAgent` reads a local tree.**
   `acp.py`'s source is a remote `repo_url` + `ref` (`acp.py:930-955`), so the
   content is what the remote serves at that ref. `OmpAgent`'s source is a local
   path (`src/harbor_omp/options.py:159`), so the content is whatever that
   working tree's HEAD happens to be — a host trust boundary `acp.py` avoids.
   The four agents that pin source *inside the container*
   (`swe_agent.py:44-52`, `deerflow.py:566-569`, `cline/cline.py:765-766`) avoid
   it the same way.
2. **`acp.py` validates what it shipped; `archive_git_head` validates what it
   read.** `acp.py` refuses a pinned-ref/SHA mismatch (`acp.py:963-964`),
   requires a validated manifest (`acp.py:1091`, `acp.py:973-978`), caps the tree
   at 10 000 files / 100 MiB and the manifest at 64 KiB (`acp.py:968-970`), and
   deletes `.git` before upload (`acp.py:966`). `archive_git_head` refuses a
   non-work-tree, uncommitted tracked changes, and a pathspec absent at HEAD
   (`src/harbor_omp/omp_agent.py:126`, `:133`, `:145`, `:154`), but ships no
   manifest and applies no size cap — its tar contains only committed content,
   which is the same *goal* as `acp.py`'s `.git` removal by a different means.
3. **The permission step is skipped.** The population that writes generated
   config sets modes: `pi.py:267` (`chmod 600` on the models file),
   `pi.py:274` (`chmod 700` on the dir), and `_upload_config_text`
   (`base.py:1036-1058`) `chown`s to the agent user and `chmod 600`s on the way
   in. The shipped tar is extracted by a shell script with no permission step
   (`src/harbor_omp/omp_agent.py:548-559`).
4. **The name collides three ways.** Harbor's CLI has a `config_source` concept
   of its own (`cli/config_sources.py` — reading a config file from a path or an
   HTTP/GitHub URL), the base class has the `config_source` property
   (`base.py:685`), and `OmpAgent`'s option is a third meaning: a host git
   checkout path (`src/harbor_omp/options.py:159`). See §10, D1.

**`[INFERENCE]`.** Whether a shipped directory is the right design is a question
this doc cannot settle. What it can say is that the *mechanism* has one
precedent (`acp.py:925-966`), the *shape* — a local checkout rather than a
remote URL — has none, and the population's dominant answer to "how does the
agent get config content the caller chose" is different: build it in the
container from typed options (`pi.py:212-353`), or hand Harbor one file
(`config=`, `native_config`, `agents/options.py:67`).

### 6.3 The clone patterns, for the container-side alternative

**`swe_agent.py:36-52`** is the reference implementation, and its docstring names
the property it preserves — "branch-first version resolution":

```
git init D && git -C D remote add origin R &&
(git -C D fetch --depth 1 origin -- "refs/heads/$revision" ||
 git -C D fetch --depth 1 origin -- "refs/tags/$revision" ||
 git -C D fetch --depth 1 origin -- "$revision") &&
git -C D checkout --detach FETCH_HEAD
```

Ref resolution order is explicit: **branch → tag → raw ref**, each `--depth 1`,
then `checkout --detach FETCH_HEAD`. Called at `swe_agent.py:414`; repo URL and
destination are module constants (`swe_agent.py:32-33`) overridable per call.

**`deerflow.py:563-580`** is simpler: `git clone --depth 1 <repo> <dir>`, then a
pinned `fetch --depth 1 origin <ref>` + `checkout --quiet FETCH_HEAD`
(`deerflow.py:566-569`), skipped entirely when `repo_ref` is empty
(`deerflow.py:563`).

**`cline/cline.py:765-766`** clones with a fallback: `git clone --branch "$REF"
--depth 1`, and a full clone + checkout if that fails.

**`acp.py:1084-1143`** is the most formal, and the only one of the four that
resolves its ref on the **host** rather than in the container (§6.1): it fetches
into a host temp dir (`acp.py:1078`), resolves `self._resolved_commit_sha`
(`acp.py:1090`), verifies a manifest (`acp.py:1091`), sets `self._version` from
it (`acp.py:1094`), writes a provenance record *before any remote step*
(`acp.py:1096-1110`), uploads the source tree (`acp.py:1116`) and runs
`uv sync --frozen` (`acp.py:1136-1142`).

**C13.** A floating ref is the exception and is named (`deerflow.py:30-33`);
the ref is an option so a caller can move it deliberately
(`deerflow.py:73-75`, `swe_agent.py:37`).

**C23.** What shipped is recorded: `acp.py:1096-1110` writes
`acp-source-provenance.json` "so setup failures and install-only runs still
record which source revision was staged"; `OmpAgent` writes three records
(`src/harbor_omp/omp_agent.py:79-82`), uploaded at
`src/harbor_omp/omp_agent.py:358-362` (plugin), `:398-402` (config) and `:579`
(the argv).

---

## 7. Secrets and credentials

### 7.1 `api_key_envs` is declared, not listed

`ModelConnectionSpec` (`model_connection.py:154`) has four fields:
`default_provider` (`:158`), `api_key_envs` (`:161`), `base_url_envs` (`:164`),
`passthrough` (`:168`). Its comments name the users — `api_key_envs`:
"claude-code, gemini-cli, openhands, mini-swe-agent"
(`model_connection.py:159-160`); `passthrough`: ten agents
(`model_connection.py:165-167`).

18 of 39 declare `MODEL_CONNECTION`; 7 of those declare `api_key_envs` (§2.4).
The agent-specific names live in the declaration because the provider defaults
cannot know them:

| agent | declaration |
|---|---|
| `claude_code.py:124-128` | `default_provider="anthropic"`, `api_key_envs=("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")`, `base_url_envs=("ANTHROPIC_BASE_URL",)` |
| `gemini_cli.py:93-98` | `default_provider="google"`, `api_key_envs=("GEMINI_API_KEY",)`, `passthrough=True` |
| `mini_swe_agent.py:508-512` | `api_key_envs=("MSWEA_API_KEY",)`, `base_url_envs=("OPENAI_BASE_URL", "OPENAI_API_BASE")` |
| `openhands.py:105-114` | `api_key_envs=("LLM_API_KEY",)`, five base-URL envs |
| `fx.py:51-54` | `api_key_envs=("AI_GATEWAY_API_KEY", "VERCEL_AI_GATEWAY_API_KEY")` |
| `muse_code.py:75-79` | `default_provider="meta"`, `api_key_envs=("META_API_KEY",)` |
| `code_puppy.py:114-117` | `api_key_envs=(_CUSTOM_API_KEY_ENV,)`, `passthrough=True` |

Provider-wide defaults live in `PROVIDERS` (`model_connection.py:15-140`), e.g.
`anthropic` → `("ANTHROPIC_API_KEY",)` with `ANTHROPIC_BASE_URL`
(`model_connection.py:26-30`), `google` → three key names
(`model_connection.py:54-63`). `_PROVIDER_ALIASES` (`model_connection.py:142`)
normalizes slugs. `resolve_model_connection` (`model_connection.py:180`) tries
the agent-specific names before the provider defaults, as the spec says
(`model_connection.py:159`).

Agents that must not receive a provider key drop it deliberately:
`aider.py:62` returns `without_provider_api_key_envs(super().model_connection)`
(`model_connection.py:285`) because "Aider injects AIDER_API_KEY itself"
(`aider.py:61`); `claude_code.py:136` and `:143` blank the inferred endpoint for
Bedrock/bearer routing (`without_inferred_endpoint`,
`model_connection.py:301`); `mini_swe_agent.py:526` exports both OpenAI
base-URL aliases when either is set.

**C25** (§3.3) is the one refinement the population adds: when config must
reference the key *symbolically*, derive the name from the resolved connection
(`pi.py:200`, `mcode.py:164`, `cline/cline.py:191`, `nemo_agent.py:95`,
`deerflow.py:244`, `code_puppy.py:205`, `vibe.py:237`) rather than adding a
static tuple.

### 7.2 Redaction

Two layers, both at the logging boundary:

- `_exec` logs the command through `_redact_command` (`base.py:968`) and redacts
  the `env` extra key-by-key with `redact_sensitive_value` /
  `is_sensitive_env_key` (`base.py:971-977`; helpers at `utils/env.py:48` and
  `utils/env.py:52`). The comment states why: "credentials (API keys etc.) are
  redacted before they reach the logging layer at all" (`base.py:972-974`).
- `_redact_command` (`base.py:898-910`) masks `Cli(sensitive=True)` values
  wherever they appear in a command line.

### 7.3 `--env-file` and job-scoped credentials

`--env-file` is a CLI option (`cli/jobs.py:961-964`). For a hosted launch the
file becomes job-scoped secrets:

- `_collect_launch_job_secrets` (`cli/hosted_jobs.py:33-50`) parses the file
  with `dotenv_values`, drops empty values, warns when nothing is left, and
  returns the mapping. Its docstring names the lifecycle: "encrypted by the
  launch API, injected into this job's trials ahead of account-wide secrets, and
  revoked when the job finishes. The key names are surfaced in the pre-launch
  summary; only names are ever displayed" (`cli/hosted_jobs.py:38-45`).
- `--one-off-secret NAME[=VALUE]` is the same channel one name at a time
  (`cli/hosted_jobs.py:57-80`); a bare `NAME` reads the value from the caller's
  environment "so a secret never has to appear in shell history"
  (`cli/hosted_jobs.py:62-64`), and the name must match `ENV_VAR_RE`
  (`cli/hosted_jobs.py:69-74`).
- The merge into the launch is at `cli/hosted_jobs.py:484-501` and
  `cli/hosted_jobs.py:550-563`. `_NO_CREDENTIAL_AGENTS`
  (`cli/hosted_jobs.py:30`, `{oracle, nop}`) exists so "a launch naming no
  credential for them is intentional rather than an omission"
  (`cli/hosted_jobs.py:27-29`), used at `cli/hosted_jobs.py:520`.
- Locally, `--env-file` is loaded with `override=True` and a missing file is a
  printed error (`cli/jobs.py:1452-1456`); a required key that is absent gets
  "Export them in your shell or pass --env-file" (`cli/jobs.py:230`), and
  explicitly-supplied file keys are tracked so the warning does not fire for
  them (`cli/jobs.py:134`, `:146`, `:190`).

### 7.4 Keys on disk

The convention is that a key does not reach the container filesystem. `junie`
states it while building its config: "Only non-secret settings go here: API keys
are supplied as environment variables so they never touch the container
filesystem" (`junie.py:441-443`). Where a config file must be uploaded,
`_upload_config_text` (`base.py:1036`) writes through a temp dir, uploads, then
`chown`s to the agent user and `chmod 600` (`base.py:1056-1057`); 7 agents use it
(`claude_code.py`, `codex.py`, `devin.py`, `fx.py`, `muse_code.py`, `pi.py`,
`strands.py`). `pi.py` adds `chmod 700` on the directory (`pi.py:274`) and a
further `chmod 600` on the models file (`pi.py:267`).

---

## 8. Failure conventions

### 8.1 The typed error hierarchy

`base.py:34-166` is one tree rooted in `RuntimeError`:

```
RuntimeError
└─ NonZeroAgentExitCodeError                    base.py:34
   ├─ ApiError                                  base.py:40
   │  ├─ ApiRateLimitError                      base.py:46
   │  ├─ ApiUsageLimitError                     base.py:57
   │  ├─ ApiInternalServerError                 base.py:65
   │  ├─ ApiOverloadedError                     base.py:73
   │  ├─ ApiConnectionClosedError               base.py:81
   │  ├─ ApiResponseStalledError                base.py:89
   │  ├─ OutputTokenExceededError               base.py:97
   │  ├─ ContextWindowExceededError             base.py:105
   │  ├─ UnknownApiError                        base.py:113
   │  ├─ ApiProviderResourceNotFoundError       base.py:121
   │  └─ AgentSafetyRefusalError                base.py:132
   ├─ AgentAuthenticationError                  base.py:145
   ├─ ModelNotFoundError                        base.py:151
   └─ NetworkConnectionError                    base.py:159
```

The docstrings say why each type is separate. `ApiRateLimitError` "lets retry
policy target it, e.g. `harbor run --max-retries 3 --retry-include
ApiRateLimitError`" (`base.py:50-53`). `AgentSafetyRefusalError` is a
deterministic decision that "will not succeed on retry, so it is excluded from
retries by default", and the distinct type keeps "a legitimate model refusal (a
real `reward 0` outcome) from reading as an unknown/flaky API error"
(`base.py:134-144`).

### 8.2 `ErrorPattern` — classification, not raising

`ErrorPattern` (`base.py:222-229`) is `(pattern, exception)`. `ERROR_PATTERNS`
(`base.py:487-580`) holds ~45 regexes. The rule is in the docstring: searched
case-insensitively over stdout and stderr, and "the match furthest toward the
end of the output wins" (`base.py:224-226`).

`_classify_exec_error` (`base.py:912`) implements it: compiled once per instance
(`base.py:661`), keeps the last match by end offset (`base.py:931-939`), and
falls back to `NonZeroAgentExitCodeError` with the redacted command and
truncated output (`base.py:918-926`, `base.py:948`). `_exec` raises that on any
non-zero exit (`base.py:999`).

**3 of 39 override `ERROR_PATTERNS`**, all three *extending*:

- `antigravity_cli.py:123-151` — `AGY_ERROR: …RESOURCE_EXHAUSTED…` patterns
  before `*BaseInstalledAgent.ERROR_PATTERNS` (`antigravity_cli.py:124`).
- `grok_build.py:246-252` — `resource-exhausted|currently at capacity`, then the
  base list (`grok_build.py:251`).
- `vibe.py:141` — `ERROR_PATTERNS = _build_error_patterns()`
  (`vibe.py:67` spreads the base list first).

### 8.3 Fail open, and narrow the evidence

`filter_jsonl_events` (`base.py:232-254`) exists so an adapter can hand the
classifier only the events the harness emitted about the failure, because "tool
output and model text embedded in the stream cannot match `ERROR_PATTERNS`"
(`base.py:238-240`); non-JSON lines are kept as-is (`base.py:245-246`), so a CLI
crash still classifies. `codex.py:396-412` uses it to keep only
`turn.failed`/`error` events before delegating (`codex.py:412`).

The classifier refuses to fire on soft evidence: `_classify_exec_error` skips
`AgentSafetyRefusalError` when the output shows a soft divert
(`base.py:927-935`), and the comment records why the needles must stay
high-precision (`base.py:545-560`).

**C18.** Classification never blocks a run: it happens on an already-failed
command, and the version probe swallows its own exceptions
(`base.py:1097-1101`). 2 of 39 raise a typed API error directly (`mimo.py`,
`opencode.py`).

### 8.4 Fail before spend

The shape is: validate inputs and pin sources, then upload, then run.

`OmpAgent` is the strongest example and is explicit about the ordering:
`install` validates the package spec and ships plugin/config sources before
`ensure_system_dependencies` (`src/harbor_omp/omp_agent.py:289-301`); a blank
`version` is refused by `package_spec` (`src/harbor_omp/options.py:38-57`) before
the install command is built; `plugin` without a name or source aborts "before
any upload and before any model spend" (`src/harbor_omp/omp_agent.py:331-340`);
so does `config_source` without `config_paths`
(`src/harbor_omp/omp_agent.py:387-394`), and an unreadable `extra_files` path
(`src/harbor_omp/omp_agent.py:416-421`); `archive_git_head`'s `_abort` message
ends the same way (`src/harbor_omp/omp_agent.py:117`).

`pi.py` shows the same discipline without the wording: `install` validates the
pinned version against the MCP adapter range and the max-turns minimum, raising
`ValueError` with the required range, **before** `ensure_system_dependencies` and
before any npm command (`pi.py:142-178`).

Across the population: every agent calls `ensure_system_dependencies` as the
first statement of `install` (`aider.py:86`, `pi.py:178`, `swe_agent.py:400`,
`junie.py:413`), and options are validated before a trial is queued by
`preflight` (`agents/base.py:222-238`) — which **0 of 39 override**, so the
base's options validation is the whole of it.

### 8.5 A no-op run is a failed run

`OmpAgent` treats "omp exited 0 without acting" as a failure, not a verdict:
`_no_op_guard_command` (`src/harbor_omp/omp_agent.py:675`) runs after a
successful launch (`src/harbor_omp/omp_agent.py:606`), exits 1 when no session
file records a tool call, and names the two causes separately — a session with
no tool call versus no session at all
(`src/harbor_omp/omp_agent.py:701-711`). The reason is dated in the comment: 22
of 30 trials on 2026-10-09 were scored reward 0 for an idle greeting
(`src/harbor_omp/omp_agent.py:598-605`). No installed agent has an equivalent;
the closest is `fx_dev.py:56-61`, which fails when the installed build is not the
dev channel.

`OmpAgent` also keeps the agent's own status: the run script is
`set -uo pipefail` without `-e`, captures `${PIPESTATUS[0]}`, saves it before the
post-commands, and re-exits with it (`src/harbor_omp/omp_agent.py:646-673`).

---

## 9. Testing conventions

### 9.1 Upstream

The installed package ships **no tests for the agents**: there is no `tests`
directory under `harbor/agents/`, and the only `test_*.py` in the package is a
task template's fixture (`harbor/cli/template-task/pytest-tests/test_outputs.py`).
No claim is made about Harbor's own repository, which is not installed.

### 9.2 This repo

The tests covering `OmpAgent` are the convention to follow, and they are listed
in `VERIFY.md`:

- **A recording environment, not a container.** `tests/conftest.py:17` defines
  `RecordingEnvironment`, a `BaseEnvironment` stand-in that records uploads and
  execs without running anything and interleaves them in call order "so a test
  can assert that something was recorded *before* something else ran"
  (`tests/conftest.py:20-23`); `tests/test_capabilities.py:10` documents the
  same split, with a `ShellEnvironment` (`tests/test_capabilities.py:46`) for
  cases that need a real POSIX shell (`_posix_shell`,
  `tests/test_capabilities.py:33`).
- **Observable behaviour only.** `AGENTS.md`, "Ground rules": "Assert observable
  behaviour (argv, uploaded bytes, recorded status, returned values), never
  source text, defaults or wiring."
- **Every check names its red case.** `VERIFY.md`'s schema comment says a check
  whose red case has not been exercised says so in the `goes-red` cell, and the
  rows carry measured red cases — e.g. the `test_plugin_ship.py` /
  `test_config_ship.py` row records "2 tests fail with `DID NOT RAISE
  ValueError`" when a dirty tree is accepted.
- **The suites**: `tests/test_capabilities.py` (resume, load, skills, MCP,
  handoff), `test_context.py`, `test_options.py`, `test_run.py`,
  `test_config_ship.py`, `test_plugin_ship.py`, `test_trajectory.py`,
  `test_session.py`, `test_hooks.py`, `test_isolation.py`, `test_noop_guard.py`,
  `test_package.py`.

### 9.3 The container smoke

CI runs ruff, `lint-imports`, pytest and an import-from-installed-distribution
probe (`.github/workflows/ci.yml`). It does **not** start a container. That job
is a script, deliberately:

- `scripts/container_smoke.py:1-17` "runs those same commands on a real
  filesystem, with the real bun and the real omp install", requires Docker and
  network, "is **not** part of CI, and it never calls a model: the agent itself
  is stubbed".
- `scripts/capability_smoke.sh:1-18` runs *inside* the benchmark image against
  real omp 18.6.0, wraps every cell in `timeout` "so a stall names itself instead
  of hanging the run", and names the four capabilities it proves.

`VERIFY.md`, "Not covered here", names what is missing rather than implying
coverage: no row re-runs a Harbor trial, ATIF correctness beyond the validator
is unverified, and `sync_trajectory` has never been run here.

---

## 10. What `OmpAgent` already does

`src/harbor_omp/omp_agent.py` is 988 lines and one class (`:224`).

### 10.1 Conventions followed

| convention | `OmpAgent` | the established pattern |
|---|---|---|
| `options_model` | `:253` (`OmpOptions`) | 39/39 (§2.2) |
| options are the contract | `src/harbor_omp/options.py:1-8` — "Harbor accepts them as `--agent-kwarg name=value`" | `agents/options.py:1-8` |
| `capabilities` declared | `:243-250` | 39/39 (§1.3) |
| `MODEL_CONNECTION` | `:251` (`passthrough=True`) | 18/39; `pi.py:98` is identical |
| `name()` / `install()` | `:274` / `:289` | the abstract pair (§1.1) |
| `get_version_command` / `parse_version` | `:278` / `:282` | 38/39 and 19/39 (§5.4) |
| `populate_context_post_run` | `:770` | 35/39 |
| `convert_trajectory` / `remote_session_logs_dir` | `:826` / `:884` | the 2 ATIF agents (§1.2) |
| `handoff` as a classmethod | `:894` | `claude_code.py:202`, `muse_code.py:440` |
| `_validate_native_load_trajectory` / `_upload_load_trajectory` | `:947` / `:977` | the 3 load-capable agents (§1.2) |
| does **not** override `resume`/`load`/`preflight`/`config_source` | absent | 0/39 override any (§1.2) |
| no `CLI_FLAGS` / `ENV_VARS` | absent | 0/39 (§2.1) |
| flags as data, not `Cli` annotations | `run_flags` (`src/harbor_omp/options.py:138`) | `pi.py` uses one `Cli(`; the population is split 23/16 (§2.3) |
| `AliasChoices` for a renamed option | `src/harbor_omp/options.py:127-129` | `pi.py:78` |
| `ensure_system_dependencies` with named packages | `:301`, names in `src/harbor_omp/install.py:26` | 36/39 (§4.2) |
| no `SYSTEM_PACKAGES` override | absent | 0/39 (§4.2) |
| `exec_as_agent` / `exec_as_root` split | `:302`, `:352` | 19/39 use root (§4.3) |
| `set -euo pipefail` on install | `src/harbor_omp/install.py:61` | 34/39 (§4.3) |
| `--ignore-scripts` on the package install | `src/harbor_omp/install.py:63` | `pi.py:193`, `pi.py:184-186` |
| print the version at the end of install | `src/harbor_omp/install.py:64` (`omp --version`) | `pi.py:195` and 6 others (§5.3) |
| pin by default, with the reason stated | `src/harbor_omp/options.py:23`, `:67-75` | `deerflow.py:30-33`, `pi.py:54-56` (§5.2) |
| measured version, not the pin | `:265` | `hermes.py:80-82` (§5.3) |
| isolated config home | `:492`, `:624` | `pi.py:409` (`PI_CODING_AGENT_DIR`) (§4.5) |
| build skills/MCP in the container | `:516-543` | `pi.py:299-353` (§3.2) |
| record provenance in the log dir | `:79-82`, `:358`, `:398`, `:579` | `acp.py:1096-1110` (§6.3) |
| secrets never written to disk | env-only key passing; `--ignore-scripts` (`src/harbor_omp/install.py:14-16`) | `junie.py:441-443` (§7.4) |
| refuse before spend | `:289-301`, `:331-340` | §8.4 |
| no-op run is a failure | `:675` | local, not upstream (§8.5) |
| container smoke outside CI | `scripts/container_smoke.py` | §9.3 |

### 10.2 Departures

Six, each with both sides.

**D1 — `config_source` names a third, unrelated thing.**
Harbor's CLI already uses the term for loading a config *file* from a path or an
HTTP/GitHub URL (`cli/config_sources.py`). The base class has a `config_source`
property (`base.py:685`) that returns Harbor's native config — a host path or
inline JSON, gated by `capabilities.native_config` (`base.py:620-623`) and read
by 5 agents. `OmpAgent`'s `options.config_source`
(`src/harbor_omp/options.py:159`) is a host path to a **git checkout** whose
committed HEAD is archived. `OmpAgent` declares no `native_config`, so the two
never interact — but a reader who knows Harbor will read the option as the
framework's concept. Its own docstring records the gap: "no native `config=`
(consumer config travels through `seed`/`config_source`)"
(`src/harbor_omp/omp_agent.py:32-35`). `[INFERENCE]`: `config_checkout` or
`config_git_ref` would collide with nothing.

**D2 — shipping a config directory at all** (§6). **This is the departure that
matters most, and it is narrower than it first looks.** `pi.py` — the nearest
relative — builds every config file in the container from options
(`pi.py:212-353`) and never reads a host checkout. Resolving a ref on the host
*is* precedented (`acp.py:925-966`), and uploading a host directory is
precedented six times (`acp.py:1116`, `eve.py:513`, `langgraph.py:397`,
`muse_code.py:344`, `nemo_agent.py:279`, `strands.py:384`). What has **no**
precedent is shipping a **local** checkout's committed HEAD as config content:
**0 of 39** run `git archive`, and `acp.py`'s source is a remote URL + ref
(`acp.py:930-955`), not a path. The six `upload_dir` callers ship source trees
and factory dirs, not config trees.

**D3 — `archive_git_head` reads a local tree; every precedent reads a remote
one.** `acp.py` runs git on the host too (`acp.py:848-889`, `_fetch_source` at
`acp.py:925-966`) but fetches from `repo_url` into a host temp dir
(`acp.py:930-955`, `acp.py:1078`) and validates the result (pinned-ref/SHA match
at `acp.py:963-964`, a manifest at `acp.py:1091`, size caps at `acp.py:968-970`).
`OmpAgent` archives `HEAD` of a **path the caller names**
(`src/harbor_omp/omp_agent.py:98-177`) — the one place it reads content from a
local working tree. Its refusals — not a work tree, a dirty tree, a pathspec
absent at HEAD (`:126`, `:133`, `:145`, `:154`) — are its whole validation, with
no manifest and no size cap; its provenance records (`:79-82`) are the
compensating control.

**D4 — the no-op guard has no upstream equivalent.**
`_no_op_guard_command` (`:675`) fails a run whose session records no tool call.
The installed agents classify *failed* commands; none inspects a successful run's
evidence and reclassifies it. `OmpAgent` therefore depends on omp's JSONL marker
(`TOOL_CALL_MARKER`, `:95`) — a coupling to one agent's log format no other agent
in the population has to its own.

**D5 — the run script carries the agent's exit status by hand.**
`_run_command` (`:646`) captures `${PIPESTATUS[0]}`, saves it before the
post-commands, and re-exits with it (`:665-673`). Every installed agent calls
`exec_as_agent` with a command whose exit status *is* the agent's — `pi.py:441-455`
pipes through `stdbuf -oL tee` and lets the pipeline status stand — so the base
`_exec` classifies it directly (`base.py:999`). `OmpAgent` interposes pre/post
command blocks, which is why the status must be carried explicitly: the cost of
the extension points in `hooks.py`.

**D6 — no `chmod` on generated config.** `pi.py` sets `chmod 600` on the models
file (`pi.py:267`) and `chmod 700` on the config dir (`pi.py:274`);
`_upload_config_text` sets `chmod 600` on upload (`base.py:1056-1057`).
`OmpAgent`'s config-home script (`:481-545`) creates the dir and writes
`agent/mcp.json` with `echo` and no mode change, and the shipped tar is extracted
with no mode step (`:548-559`).

---

## 11. Disagreements and non-consensus

Counts, not averages.

| # | disagreement | counts |
|---|---|---|
| 1 | credential declaration | 18 declare `MODEL_CONNECTION`, of which 7 declare `api_key_envs`; 21 declare neither; 11 override the `model_connection` property. `claude_code.py:126` is the only one naming **two** API-key envs for one provider |
| 2 | static list vs derived name | 7 declare a static `api_key_envs` tuple; 7 derive the name from the connection or a provider table (`pi.py:200`, `mcode.py:164`, `cline/cline.py:191`, `nemo_agent.py:95`, `deerflow.py:244`, `code_puppy.py:205`, `vibe.py:237`); 25 do neither. Only `pi.py:245` needs the name, because only it writes `apiKey: "$VAR"` |
| 3 | by value vs symbolic | 14 pass the resolved env through (`access.env` / `model_connection.env`); 1 writes a `$VAR` reference (`pi.py:245`). `OmpAgent` is in the by-value camp (`src/harbor_omp/omp_agent.py:591`) |
| 4 | `Cli` vs `Env` | 23 use `Cli(`, 6 use `Env(`; only `claude_code.py` mixes both (9 and 1). `openhands.py` uses 10 `Env(` and no `Cli(` |
| 5 | how a version is reported | 38 override `get_version_command`, 19 also `parse_version`, 19 override neither. `acp.py` overrides neither and derives `_version` from a registry entry (`acp.py:498`) or manifest (`acp.py:1094`) |
| 6 | version-pin default | 35 leave `version=None` (`@latest`); 3 pin by constant/option default (`deerflow.py:33`, `claude_code.py:151`, `openhands.py:89`); `OmpAgent` is the only one that refuses to run unpinned (`src/harbor_omp/options.py:67-75`) |
| 7 | system dependencies | 36 call `ensure_system_dependencies`; 3 do their own package work (`acp.py`, `cline/cline.py:815-830`, `kimi_code.py:65-92`). Nobody overrides `SYSTEM_PACKAGES` |
| 8 | install style for one vendor | `claude_code.py:481-485` branches npm vs a curl bootstrap on whether `apk` exists; `codex.py:429-441` branches npm vs nvm+npm on musl. Two agents, two different musl probes |
| 9 | `parse_version` shape | last non-empty line (`pi.py:129`, `code_puppy.py:141`, `junie.py:404`) vs a `\d+.\d+.\d+` regex (`copilot_cli.py:79`, `cortex_code.py:686`, `goose.py:121`) vs `stdout.strip()` (`openhands_sdk.py:123`) — no shared helper exists |
| 10 | `ERROR_PATTERNS` | 3 extend it, 36 inherit. `grok_build.py:246` and `vibe.py:67` prepend/append; `antigravity_cli.py:124` spreads the base first |
| 11 | ATIF | 32 declare `atif=True`; 7 do not (`aider.py:55`, `code_puppy.py:107`, `fx.py:49`, `langgraph.py:95`, `mcode.py:42`, `openclaw.py:364`) |
| 12 | `windows` | declared by **0** agents, though `capabilities.py:37` defines it and `agents/base.py:70` carries the legacy alias — a field with no users |
| 13 | idempotency | 3 probe and skip (`claude_code.py:451`, `codex.py:403`, `deerflow.py:124`); 36 reinstall unconditionally |
| 14 | generated-config permissions | `pi.py:267`/`:274` and `_upload_config_text` (`base.py:1056-1057`) set modes; `goose.py:138-161` writes a heredoc with none; `OmpAgent` sets none (`src/harbor_omp/omp_agent.py:525-543`) |
| 15 | `native_config` vs reading `config_source` | the two sets coincide exactly (5 agents, §2.4) — the one place the population is unanimous, and `OmpAgent` is outside it (§10.2 D1) |
| 16 | setup timeout | 1 of 39 raises `DEFAULT_SETUP_TIMEOUT_SEC` (`hermes.py:97`, 1200 s, reason at `hermes.py:94-96`); 38 keep 360 s (`agents/base.py:59`) |
| 17 | host→container content | 6 upload a directory, 12 upload a file, 5 take Harbor's native `config`; 1 (`acp.py:925-966`) resolves a git ref on the host; **0** archive a local checkout. Four mechanisms for one job |

---

## 12. Could not verify

1. **Harbor's own test suite.** The installed package ships no agent tests
   (§9.1). Whether upstream has container smoke tests, and what they assert, is
   not knowable from the installed artifact — no claim is made.
2. **Why individual agents chose a style.** Where this doc says "two agents, two
   different musl probes" it reports the code; the reasoning is not in the
   package. Marked `[INFERENCE]` where a motive is suggested (§6.2, §10.2 D1).
3. **Whether any agent's install actually works.** Nothing here ran a container
   or an install. Every install claim cites a command string, not a measured
   outcome.
4. **`windows=True`.** No agent declares it and no environment code path was
   read, so the field's intended users are unknown.
5. **Whether a shipped config directory is *right*.** §6.1 establishes that it is
   precedented in mechanism (`acp.py`) and unprecedented in shape (a local
   checkout); it cannot establish that the shape is wrong. That judgement belongs
   to the design review, and this doc only removes "no precedent at all" as an
   argument either way.
6. **The parent brief's line anchors.** Three did not match the installed version
   and are corrected in §0 (`_build_clone_command`, `SYSTEM_DEPENDENCIES`,
   `abstract install()`).
7. **`fx_dev.py`.** It subclasses `Fx` (not `BaseInstalledAgent` directly), has
   its own `options_model` (`fx_dev.py:29`) and an `install` override
   (`fx_dev.py:39`). It is counted among the 15 support modules; if it should
   count as a 40th agent, the counts move by one.
8. **Whether Harbor registers all 39.** No registry module was read, so
   `harbor agents` may expose a subset. The 39 is the count of classes deriving
   from `BaseInstalledAgent` in the installed directory.
9. **How `config=` reaches a constructor in a live trial.** `_constructor_kwargs`
   (`agents/factory.py:24-32`) merges `AgentConfig.kwargs` (`models/trial/config.py:148`)
   with framework kwargs, and `config` is a keyword-only parameter of
   `BaseInstalledAgent.__init__` (`base.py:594`) and a field of
   `InstalledAgentOptions` (`agents/options.py:67`) — so `--ak config=<path>` is
   the path in, but the end-to-end call site was not traced. `[INFERENCE]` on
   that being the only route.
10. **The eval-config-from-git-ref change itself.** This document describes
    conventions; it does not evaluate the change beyond §6 and §10.2 D1–D2.
