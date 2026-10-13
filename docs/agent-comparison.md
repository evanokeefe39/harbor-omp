# How Harbor's installed agents receive config and declare credentials

A six-way comparison of `claude_code`, `codex`, `hermes`, `pi`, `opencode` and
`gemini_cli`, read against `OmpAgent`, the custom installed agent in this repo.
The question behind it: `OmpAgent` is about to change how it receives its config,
and it must follow the conventions these agents actually established rather than
invent a house style.

## Scope and method

**Compared.** The six agents named above, plus `OmpAgent` as a seventh column so
every dimension shows whether it conforms or departs.

**Sources, read in this session (read-only).**

| shorthand | path |
|---|---|
| `claude_code.py` … `gemini_cli.py` | `.venv/Lib/site-packages/harbor/agents/installed/<name>.py` |
| `base.py` | `.venv/Lib/site-packages/harbor/agents/installed/base.py` (1246 lines) |
| `../base.py` | `.venv/Lib/site-packages/harbor/agents/base.py` (417 lines) |
| `../model_connection.py` | `.venv/Lib/site-packages/harbor/agents/model_connection.py` (312 lines) |
| `../capabilities.py` | `.venv/Lib/site-packages/harbor/agents/capabilities.py` (54 lines) |
| `../options.py` | `.venv/Lib/site-packages/harbor/agents/options.py` |
| `omp_agent.py`, `options.py` (bare) | `src/harbor_omp/omp_agent.py` (988 lines), `src/harbor_omp/options.py` (242 lines) |
| `install.py` (bare) | `src/harbor_omp/install.py` |

`install.py` and bare `options.py` are `harbor_omp`; every other unqualified name
is under `installed/`.

**Method.** Each of the six was read in full or in the ranges that carry the
dimension, and structural anchors were grepped so the counts are real rather than
recalled: `class `, `api_key_envs`, `_api_key_env_name`, `CliFlag(`, `EnvVar(`,
`capabilities`, `MODEL_CONNECTION`, `config_source`, `def install`, `async def
run`, `_ensure_config_dir`, `convert_trajectory`, `populate_context_post_run`,
`handoff`, `resume`, `load`, `CLI_FLAGS`, `ENV_VARS`, `ERROR_PATTERNS`,
`SYSTEM_PACKAGES`, `build_cli_flags`, `remote_session_logs_dir`.

**Counts.** `installed/` holds 51 `.py` files, of which **38 declare a
`BaseInstalledAgent` subclass** (the rest are shared helpers: `base.py`,
`node_install.py`, the `acp*` runner modules). A package-wide count is therefore
stated as "N of 38 installed agents", and a grep over the directory's files is
stated as "over all 51 `.py` files". Where a verdict needs "is this a
convention?", the grep was widened from the six to the whole `installed/`
directory, and those wider counts are labelled as such.

**Line counts** (`wc -l`): `claude_code.py` 1976, `codex.py` 1808, `hermes.py`
561, `pi.py` 1065, `opencode.py` 634, `gemini_cli.py` 1024, `omp_agent.py` 988.

## The matrix

| dimension | claude_code | codex | hermes | pi | opencode | gemini_cli | **OmpAgent** |
|---|---|---|---|---|---|---|---|
| module / lines | `claude_code.py` 1976 | `codex.py` 1808 | `hermes.py` 561 | `pi.py` 1065 | `opencode.py` 634 | `gemini_cli.py` 1024 | `omp_agent.py` 988 |
| class | `ClaudeCode` `claude_code.py:112` | `Codex` `codex.py:112` | `Hermes` `hermes.py:61` | `Pi` `pi.py:91` | `OpenCode` `opencode.py:56` | `GeminiCli` `gemini_cli.py:77` | `OmpAgent` `omp_agent.py:224` |
| base | `BaseInstalledAgent, ACPAgentMixin` `claude_code.py:112` | `BaseInstalledAgent, ACPAgentMixin` `codex.py:112` | `BaseInstalledAgent` `hermes.py:61` | `BaseInstalledAgent` `pi.py:91` | `BaseInstalledAgent, ACPAgentMixin` `opencode.py:56` | `BaseInstalledAgent, ACPAgentMixin` `gemini_cli.py:77` | `BaseInstalledAgent` `omp_agent.py:224` |
| options model | `ClaudeCodeOptions` `claude_code.py:53`; 12 fields | `CodexOptions` `codex.py:73`; 5 fields | `HermesOptions` `hermes.py:48`; 2 fields | `PiOptions` `pi.py:72`; 3 fields | `OpenCodeOptions` `opencode.py:44`; 3 fields | `GeminiCliOptions` `gemini_cli.py:59`; 3 fields | `OmpOptions` `options.py:62`; 13 fields |
| fields added | max_turns, reasoning_effort, thinking_display, max_budget_usd, fallback_model, append_system_prompt, allowed_tools, disallowed_tools, disable_web_search, permission_mode, max_thinking_tokens, memory_dir `claude_code.py:54-109` | reasoning_effort, reasoning_summary, web_search, disable_web_search, dangerously_bypass_hook_trust `codex.py:74-101` | toolsets, max_turns `hermes.py:49-56` | thinking, model_api, max_turns `pi.py:73-87` | variant, opencode_config, disable_web_search `opencode.py:45-53` | disable_web_search, sandbox, reasoning_effort `gemini_cli.py:60-73` | version, thinking, run_flags, install_only, config_source, config_paths, plugin, seed, config_home, session_dir_name, extra_files, pre_commands, post_commands `options.py:125-241` |
| options base | `InstalledAgentOptions` (`../options.py:56`) for all six; adds `version`, `prompt_template_path`, `config` (`../options.py:59-69`) | ← same | ← same | ← same | ← same | ← same | ← same; `version` is defaulted and validated (`options.py:65-75`) |
| install style | npm **or** curl bootstrap: `npm install -g @anthropic-ai/claude-code@<v>` on apk, else `curl -fsSL https://downloads.claude.ai/claude-code-releases/bootstrap.sh \| bash -s -- <v>` `claude_code.py:477-489` | npm (musl) else curl-nvm then `npm install -g @openai/codex@<v>` `codex.py:426-441`; root symlink step `codex.py:445-456` | curl install script: `curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh \| bash -s -- --skip-setup --branch <v>` `hermes.py:117-128` | npm via nvm: `npm install -g --ignore-scripts @earendil-works/pi-coding-agent@<v>` `pi.py:191-196` | npm (musl-aware): `npm i -g opencode-ai@<v>` `opencode.py:143-152` | npm via nvm: `npm install -g @google/gemini-cli@<v>` `gemini_cli.py:172-179` | bun: `bun install -g --ignore-scripts <spec>` `install.py:61-65` |
| `ensure_system_dependencies` | `("curl","bash","nodejs","npm","procps")` `claude_code.py:473-475` | `("curl","bash","nodejs","npm","ripgrep")` `codex.py:422-424` | `("curl","git","ripgrep","xz")` `hermes.py:114-116` | `("curl",)` `pi.py:178` | `("curl","bash","coreutils","nodejs","npm")` `opencode.py:134-137` | `("curl",)` `gemini_cli.py:171` | `("curl","git","unzip")` `install.py:26`, called `omp_agent.py:301` |
| version pin splice | `@{v}` npm / ` {v}` bootstrap `claude_code.py:483-485` | `@{v}` else `@latest` `codex.py:426` | `--branch {v}` — a git branch, not a version `hermes.py:117` | `@{v}` else `@latest`, package rename below 0.74.0 `pi.py:131-139,179` | `@{v}` else `@latest` `opencode.py:137` | `@{v}` else `@latest` `gemini_cli.py:172` | `package_spec(version)`, default `@oh-my-pi/pi-coding-agent@18.6.0` `options.py:23,38-48,125-132` |
| `get_version_command` | `export PATH=…; claude --version` `claude_code.py:412-413` | nvm-sourced `codex --version` `codex.py:373-374` | `export PATH=…; hermes version` `hermes.py:109-110` | `. ~/.nvm/nvm.sh; pi --version` `pi.py:124-125` | nvm-optional `opencode --version` `opencode.py:125-127` | nvm-optional `gemini --version` `gemini_cli.py:83-84` | `install.version_command()` → `bun …; omp --version 2>/dev/null \|\| echo 'not installed'` `omp_agent.py:278-279`, `install.py:71-74` |
| `parse_version` | regex `(\d+\.\d+\.\d+)` `claude_code.py:416-425` | strips `codex-cli` prefix `codex.py:377-383` | base default `stdout.strip()` `base.py:878-881` | last non-empty line `pi.py:128-129` | base default `base.py:878-881` | base default `base.py:878-881` | last non-empty line `install.py:77-81` |
| version measured or claimed | measured **and verified** against the pin: re-probe + compare `claude_code.py:451-463` | measured **and verified**: re-probe + compare `codex.py:402-414` | measured only when no pin; a pin is reported as-is `base.py:1093-1100` | same as hermes | same as hermes | same as hermes | **always measured**: `__init__` forces `self._version = None` `omp_agent.py:258-265` |
| `MODEL_CONNECTION` | `default_provider="anthropic"`, `api_key_envs=("ANTHROPIC_API_KEY","ANTHROPIC_AUTH_TOKEN")`, `base_url_envs=("ANTHROPIC_BASE_URL",)` `claude_code.py:124-128` | `ModelConnectionSpec(default_provider="openai")` `codex.py:132` | **absent** (class declares no `MODEL_CONNECTION`) `hermes.py:61-66` | `ModelConnectionSpec(passthrough=True)` `pi.py:98` | `ModelConnectionSpec(passthrough=True)` `opencode.py:79` | `default_provider="google"`, `api_key_envs=("GEMINI_API_KEY",)`, `base_url_envs=("GOOGLE_GEMINI_BASE_URL",)`, `passthrough=True` `gemini_cli.py:93-97` | `ModelConnectionSpec(passthrough=True)` `omp_agent.py:251` |
| `capabilities` true flags | atif, resume, load_native_trajectory, load_atif_trajectory, handoff, native_config, skills, mcp_servers, bridges=ACP `claude_code.py:113-123` | atif, resume, load_native, load_atif, native_config, skills, mcp_servers, bridges=ACP `codex.py:122-131` | atif, resume, skills, mcp_servers `hermes.py:64-66` | atif, resume, skills, mcp_servers `pi.py:92-97` | atif, resume, skills, mcp_servers, bridges=ACP `opencode.py:72-78` | atif, resume, bridges=ACP, skills, mcp_servers `gemini_cli.py:86-92` | atif, resume, load_native_trajectory, skills, mcp_servers, handoff `omp_agent.py:243-250` |
| config delivery shape | in-container from options **+** a native settings file from `config_source` `claude_code.py:377-411` | in-container from options **+** a native TOML from `config_source` `codex.py:1536-1626` | in-container only: generated `config.yaml` `hermes.py:135-168,472-478` | in-container only: models JSON, mcp JSON, extension `.ts` `pi.py:212-343` | in-container only: `opencode.json` `opencode.py:521-575` | in-container only: `settings.json` `gemini_cli.py:764-833` | **directory ship**: `git archive` of a host checkout, uploaded as a tar, extracted after the home reset `omp_agent.py:98-181,364-402,548-563` |
| uses `config_source` | **yes** (11 refs) `claude_code.py:379-401,1905,1926,1965` | **yes** (9 refs) `codex.py:1538-1569` | no (0 refs) | no (0 refs) | no (0 refs) | no (0 refs) | yes, but a **different** object: an `OmpOptions` field, not the base property `options.py:159-169` |
| API key declaration | static tuple `claude_code.py:126` | static via provider table (`OPENAI_API_KEY` `../model_connection.py:100-104`), no `api_key_envs` `codex.py:132` | **neither** — hand-rolled `_NATIVE_PROVIDERS` map read from `os.environ` `hermes.py:34-42,445-460` | derived `_api_key_env_name(access)` `pi.py:200-209` | none (passthrough only) `opencode.py:79` | static tuple `gemini_cli.py:95` | **none** (passthrough only) `omp_agent.py:251`; no `api_key` reference in the module |
| `CliFlag` / `EnvVar` classvars | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| `Cli()` / `Env()` annotations | 9 / 1 `claude_code.py:54-109` | 4 / 0 `codex.py:74-101` | 2 / 0 `hermes.py:49-56` | 1 / 0 `pi.py:73-79` | 1 / 0 `opencode.py:45-47` | 1 / 0 `gemini_cli.py:64-67` | 0 / 0 (none anywhere in `options.py`) |
| `build_cli_flags()` compiled in `run()` | yes `claude_code.py:1922` | yes `codex.py:1671` | **no** — never called; `--toolsets` hand-rendered `hermes.py:525`, `max_turns` goes into YAML `hermes.py:470` | yes `pi.py:426` | yes `opencode.py:612` | yes `gemini_cli.py:975` | **no** — no flags to compile; argv is a list `omp_agent.py:736-768` |
| config-dir handling | `$CLAUDE_CONFIG_DIR` = `<logs>/sessions` `claude_code.py:1895`; `mkdir` block `claude_code.py:1897-1904` | `$CODEX_HOME` = `/tmp/codex-home` `codex.py:134,1685-1690` | `HERMES_HOME=/tmp/hermes` `hermes.py:114-124,429-431` | `PI_CODING_AGENT_DIR=/tmp/harbor-pi-agent` `pi.py:46-47,406-409` **+ `_ensure_config_dir`** `pi.py:270-275` | `~/.config/opencode` `opencode.py:516,574` | `~/.gemini` `gemini_cli.py:182-190,749-751` | isolated HOME `/tmp/omp-home` + `PI_CONFIG_DIR=.omp` `omp_agent.py:86,425-434`; reset+seed+extract `omp_agent.py:481-563` |
| `_ensure_config_dir` | absent | absent | absent | present `pi.py:270` | absent | absent | absent (uses `_config_home_command` `omp_agent.py:481`) |
| skills | `_build_register_skills_command` → `$CLAUDE_CONFIG_DIR/skills/` `claude_code.py:1688-1700`; memory dir too `claude_code.py:1702-1715` | → `$HOME/.agents/skills` `codex.py:1526-1536` | → `/tmp/hermes/skills` `hermes.py:190-197` | → `$HOME/.agents/skills` `pi.py:345-353` | → `~/.config/opencode/skills` `opencode.py:511-519` | → `~/.gemini/skills` `gemini_cli.py:743-751` | → `<config_dir>/agent/skills` `omp_agent.py:511-520` |
| MCP servers | `$CLAUDE_CONFIG_DIR/.claude.json` `claude_code.py:1717-1743` | merged into `config.toml` `mcp_servers` `codex.py:1583-1610` | appended to `config.yaml` `hermes.py:170-187` | `mcp.json` in config dir `pi.py:277-305` | into `opencode.json` `mcp` `opencode.py:529-550` | into `settings.json` `mcpServers` `gemini_cli.py:781-792` | `<config_dir>/agent/mcp.json` `omp_agent.py:522-546` |
| extension points | ACP bridge, memory dir, `config_source` | ACP bridge, `config_source`, `auth.json` injection `codex.py:1628-1658` | none beyond options | max-turns `.ts` extension `pi.py:310-343`; `pi-mcp-adapter` extension `pi.py:56-58,413-415` | `opencode_config` deep-merge overlay `opencode.py:110-119,551-561` | model-alias + thinking config in settings `gemini_cli.py:753-822` | `plugin`, `seed`, `extra_files`, `pre_commands`, `post_commands` `options.py:180-241` |
| `run()` argv | `claude --verbose --output-format=stream-json <--settings> <cli_flags> <--continue> --print`, instruction through an env var `claude_code.py:1944-1970` | `codex exec [resume --last] --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --model <m> --json --enable unified_exec <cli_flags> -- <instruction>` `codex.py:1764-1778` | `hermes --yolo chat [--resume <id>] -q "$HARBOR_INSTRUCTION" -Q --model <m> [--provider p] [--toolsets t]` `hermes.py:503-533` | `pi --print --mode json --session-dir <dir> [--continue] --provider <p> --model <m> [--extension …] <cli_flags> <instruction>` `pi.py:443-457` | `opencode --model=<m> run --format=json [--continue] <cli_flags>--thinking --dangerously-skip-permissions -- <instruction>` `opencode.py:619-628` | `gemini --yolo [--resume latest] <cli_flags>--model=<alias\|m> --prompt=<instruction>` `gemini_cli.py:982-990` | `omp -p --auto-approve <run_flags> --session-dir=<dir> --model=<provider/model> [--thinking=<v>] [--continue] [--resume <stem>] <instruction>` `omp_agent.py:736-768` |
| prompt templating | `@with_prompt_template` `claude_code.py:1861` | `@with_prompt_template` `codex.py:1659` | `@with_prompt_template` `hermes.py:416` | `@with_prompt_template` `pi.py:376` | `@with_prompt_template` `opencode.py:577` | `@with_prompt_template` `gemini_cli.py:937` | `@with_prompt_template` `omp_agent.py:566` |
| `populate_context_post_run` | override `claude_code.py:1657` | override `codex.py:1492` | override `hermes.py:363` | override `pi.py:460` | override `opencode.py:478` | override `gemini_cli.py:696` | override `omp_agent.py:770` |
| `convert_trajectory` | override `claude_code.py:606` | override `codex.py:573` | not overridden | not overridden | not overridden | not overridden | override `omp_agent.py:826` |
| `remote_session_logs_dir` | override `claude_code.py:602` | override `codex.py:569` | not overridden | not overridden | not overridden | not overridden | override `omp_agent.py:884` |
| `_convert_session_events_to_trajectory` | absent | absent | absent | present `pi.py:733` | absent | absent | absent (delegates to `trajectory.convert_trajectory` `omp_agent.py:840`) |
| failure behaviour | `ValueError` at construction for a bad load file `claude_code.py:179-192`; `RuntimeError` in `run()` before launch when `CLAUDE_FORCE_OAUTH` lacks a token `claude_code.py:1792-1796`; `_classify_exec_error` override `claude_code.py:427-449` | `ValueError` at construction for bad config `codex.py:1557-1566`; `ValueError` in `run()` for a missing model `codex.py:1665-1666`; `_classify_exec_error` override `codex.py:386-400` | `ValueError` in `run()` for a malformed model name `hermes.py:426-427` and for no usable key `hermes.py:455-464`; `RuntimeError` on resume of a pinned version `hermes.py:508-513` | `ValueError` in `install()` for an out-of-range version — before install `pi.py:143-177`; `ValueError` in `run()` for a malformed model name `pi.py:385-386` and for a custom endpoint missing `model_api`/base URL/key env `pi.py:213-231` | `ValueError` in `run()` for a malformed model name `opencode.py:590-591`; `NonZeroAgentExitCodeError` **after** the run on error events `opencode.py:632-634` | `ValueError` at construction for a bad reasoning effort `gemini_cli.py:140-168`; `ValueError` in `run()` for a malformed model name `gemini_cli.py:946-947` | `ValueError` at construction from `OmpOptions` validators `options.py:65-122`; aborts **before upload and before spend** for an unpinnable plugin/config source `omp_agent.py:289-300,360-402` and for a missing `extra_files` path `omp_agent.py:404-422`; post-run no-op guard fails a run by design `omp_agent.py:675-727` |
| fails before model spend | yes for auth/config validation; install failure fails setup `claude_code.py:466-491` | yes for config validation; install failure fails setup `codex.py:417-456` | yes — key check precedes the launch `hermes.py:455-464` | yes — version gate precedes the install `pi.py:143-177` | partly — model-name check yes, error-event check is post-spend `opencode.py:590,632` | yes — construction-time checks `gemini_cli.py:140-168` | yes, and the abort is explicit about it `omp_agent.py:115-118` |
| resume | `--continue` `claude_code.py:1929` | `resume --last` `codex.py:1702,1766` | `--resume <native id>` `hermes.py:507-513` | `--continue` `pi.py:429` | `--continue` `opencode.py:614` | `--resume latest` `gemini_cli.py:978` | `--continue` `omp_agent.py:756-757` |
| load native | yes, + ATIF `claude_code.py:116-117,1937-1939` | yes, + ATIF `codex.py:125-126,1700-1701` | no | no | no | no | yes, native only `omp_agent.py:244-249,574-575,760-762,947-988` |
| handoff | classmethod `claude_code.py:202-226` | not declared | not declared | not declared | not declared | not declared | classmethod `omp_agent.py:894-928` |
| setup timeout | base default 360 s `../base.py:59` | base default | `DEFAULT_SETUP_TIMEOUT_SEC = 1200.0` `hermes.py:97` | base default | base default | base default | base default |

## Where all six agree

Real agreement counts, each cited.

1. **All six subclass `BaseInstalledAgent` and declare `options_model`** (6 of 6)
   — `claude_code.py:159`, `codex.py:147`, `hermes.py:68`, `pi.py:104`,
   `opencode.py:91`, `gemini_cli.py:119`. The options model is the declared
   surface for everything the agent accepts; `OmpAgent` conforms
   (`omp_agent.py:253`).
2. **All six declare `capabilities` with `atif`, `resume`, `skills` and
   `mcp_servers` true** (6 of 6) — `claude_code.py:113-123`, `codex.py:122-131`,
   `hermes.py:64-66`, `pi.py:92-97`, `opencode.py:72-78`, `gemini_cli.py:86-92`.
   `OmpAgent` conforms on all four (`omp_agent.py:243-250`).
3. **None of the six declares `CLI_FLAGS` or `ENV_VARS`** (0 of 6) — grep across
   the six returns nothing, and the base forbids the combination outright:
   `options_model` together with `CLI_FLAGS`/`ENV_VARS` raises in
   `__init_subclass__` (`base.py:585-592`). The whole package agrees: `CLI_FLAGS`
   appears only in `base.py`. Flags are declared as `Cli()`/`Env()` annotations on
   the options model (`../options.py:16-43`) and compiled by `build_cli_flags()`
   (`base.py:817-837`). `OmpAgent` conforms by declaring zero of both.
4. **All six install with a shell command and call `ensure_system_dependencies`
   first** (6 of 6) — `claude_code.py:473`, `codex.py:422`, `hermes.py:114`,
   `pi.py:178`, `opencode.py:134`, `gemini_cli.py:171`. None declares
   `SYSTEM_PACKAGES` (0 of 6); the base's map (`base.py:363`) is used only
   through the explicit tuple. `OmpAgent` conforms (`omp_agent.py:301`,
   `install.py:26`).
5. **All six splice a caller-supplied version into the install command** (6 of 6)
   — `claude_code.py:483-485`, `codex.py:426`, `hermes.py:117`, `pi.py:179`,
   `opencode.py:137`, `gemini_cli.py:172`. `OmpAgent` conforms, with a defaulted
   and validated option (`options.py:125-132`).
6. **All six declare `get_version_command`** (6 of 6) — `claude_code.py:412`,
   `codex.py:373`, `hermes.py:109`, `pi.py:124`, `opencode.py:125`,
   `gemini_cli.py:83`. `OmpAgent` conforms (`omp_agent.py:278-279`).
7. **All six override `populate_context_post_run`** (6 of 6) —
   `claude_code.py:1657`, `codex.py:1492`, `hermes.py:363`, `pi.py:460`,
   `opencode.py:478`, `gemini_cli.py:696`. `OmpAgent` conforms
   (`omp_agent.py:770`).
8. **All six register skills with a shell `cp -r` builder named
   `_build_register_skills_command`** (6 of 6) — `claude_code.py:1688`,
   `codex.py:1526`, `hermes.py:190`, `pi.py:345`, `opencode.py:511`,
   `gemini_cli.py:743`. This is the strongest single convention in the six: the
   method name, the `None`-when-unset guard and the `2>/dev/null || true`
   tolerance are identical everywhere. `OmpAgent` **departs** by inlining the
   copy into `_config_home_command` (`omp_agent.py:511-520`) and keeping no such
   method.
9. **All six build MCP config in-container from `self.mcp_servers`** (6 of 6) —
   `claude_code.py:1717-1743`, `codex.py:1583-1610`, `hermes.py:170-187`,
   `pi.py:277-305`, `opencode.py:529-550`, `gemini_cli.py:781-792`. The target
   file differs but the shape does not: iterate `self.mcp_servers`, branch on
   `transport == "stdio"` vs url, emit JSON/YAML/TOML. `OmpAgent` conforms
   (`omp_agent.py:522-546`).
10. **All six apply `@with_prompt_template` to `run()`** (6 of 6) —
    `claude_code.py:1861`, `codex.py:1659`, `hermes.py:416`, `pi.py:376`,
    `opencode.py:577`, `gemini_cli.py:937`. `OmpAgent` conforms
    (`omp_agent.py:566`).
11. **All six deliver config by writing files in-container from options-derived
    values, never by shipping a host directory** (6 of 6) — see each agent's
    config builder in the matrix. Across the whole `installed/` package, no agent
    runs `git archive`, `tarfile`, or any host-directory archive: grep for
    `git archive|archive_git_head|tarfile` over all 51 `.py` files returns **zero
    files**. `OmpAgent` **departs** here (see Question 1).

## Where they split

### `ACPAgentMixin` — 4 of 6

`claude_code` (`claude_code.py:112`), `codex` (`codex.py:112`), `opencode`
(`opencode.py:56`) and `gemini_cli` (`gemini_cli.py:77`) mix in `ACPAgentMixin`
and implement `acp_command` (`claude_code.py:514`, `codex.py:459`,
`opencode.py:155`, `gemini_cli.py:202`). `hermes` and `pi` do not, and declare no
`bridges` capability. `OmpAgent` sits with `hermes`/`pi`
(`omp_agent.py:224,243-250`).

### `MODEL_CONNECTION` — 5 of 6 declare one; `hermes` declares none

`claude_code.py:124-128`, `codex.py:132`, `pi.py:98`, `opencode.py:79`,
`gemini_cli.py:93-97`. `hermes` has no `MODEL_CONNECTION` at all
(`hermes.py:61-66`), so its inherited `model_connection` returns an empty
`ResolvedModelConnection` (`../base.py:281-288`) and it resolves credentials
itself from `os.environ` through `_NATIVE_PROVIDERS` (`hermes.py:38-45`) plus a
hand-written OpenRouter fallback (`hermes.py:455-465`). `OmpAgent` declares one
(`omp_agent.py:251`).

### API key declaration — 2 static, 1 derived, 3 none

See Question 2 for the verdict; the camps are set out there.

### `config_source` — 2 of 6

`claude_code` and `codex` use Harbor's `config_source` property
(`base.py:684-687`), which is fed by the `config=` constructor kwarg
(`base.py:594-608`) and gated on `capabilities.native_config`
(`base.py:620`). They are the only two of the six with `native_config=True`
(`claude_code.py:119`, `codex.py:127`). `hermes`, `pi`, `opencode` and
`gemini_cli` never mention it (0 references each). `OmpAgent` does **not** declare
`native_config` (`omp_agent.py:243-250`), so Harbor's own path raises for it
(`base.py:620`) — see Question 1.

### `load_native_trajectory` / `load_atif_trajectory` — 2 of 6

`claude_code` (`claude_code.py:116-117`) and `codex` (`codex.py:125-126`) declare
both and call `_seed_load_trajectory` from `run()` (`claude_code.py:1937-1939`,
`codex.py:1700-1701`). The other four declare neither. `OmpAgent` declares native
only (`omp_agent.py:245`), which its module docstring states as a deliberate
limitation ("no load ATIF (lossy conversion)", `omp_agent.py:32-33`), and calls
`_seed_load_trajectory` itself (`omp_agent.py:574-575`).

### `handoff` — 1 of 6

Only `claude_code` declares `handoff=True` and implements the classmethod
(`claude_code.py:118,202-227`). `codex`, `hermes`, `pi`, `opencode` and
`gemini_cli` declare it false. `OmpAgent` declares it true and implements it
(`omp_agent.py:249,894-928`) — it follows `claude_code`'s shape (a
`shutil.which` guard, a single-session requirement, `copyfile`, a resume argv) and
differs only in the local destination (`~/.omp/sessions`, respecting
`PI_CONFIG_DIR`, `omp_agent.py:921-928`).

### `convert_trajectory` — 2 of 6 override it

`claude_code.py:606` and `codex.py:573`. The other four convert only in
`populate_context_post_run` (`hermes.py:363`, `pi.py:460`, `opencode.py:478`,
`gemini_cli.py:696`) through private helpers (`_convert_hermes_session_to_atif`
`hermes.py:203`, `_convert_session_events_to_trajectory` `pi.py:733`,
`_convert_events_to_trajectory` `opencode.py:260`, `_convert_gemini_to_atif`
`gemini_cli.py:321`). `OmpAgent` overrides it (`omp_agent.py:826`) — the camp of
two, not the camp of four.

### `remote_session_logs_dir` — 2 of 6 override it

`claude_code.py:602`, `codex.py:569`; the other four inherit the `None` default
(`base.py:351-354`). `OmpAgent` overrides it (`omp_agent.py:884`).

### `parse_version` — 3 of 6 override it

`claude_code.py:416` (regex), `codex.py:377` (prefix strip), `pi.py:128` (last
line). `hermes`, `opencode` and `gemini_cli` take the base default
`stdout.strip()` (`base.py:878-881`). `OmpAgent` overrides it via
`install.parse_version` (`omp_agent.py:282-283`, `install.py:77-81`).

### Install style — npm 4, curl-script 2, bun 1

`codex.py:426-441`, `pi.py:191-196`, `opencode.py:143-152`, `gemini_cli.py:172-179`
are npm installs (three of them through `nvm_node_install_snippet`,
`pi.py:14,191`). `claude_code.py:477-489` is npm on apk and a curl bootstrap
script elsewhere. `hermes.py:117-128` is a curl install script from GitHub raw
(the only *clone-shaped* install: the comment at `hermes.py:94-96` records that
`install.sh` clones the repo and resolves the toolchain with uv). `OmpAgent` uses
bun (`install.py:61-65`), which is correct for omp — it is a bun tool — and is the
only bun install in the package.

### Version verification — 2 of 6 verify the pin

`claude_code` and `codex` re-probe the installed CLI and compare it to the
requested version before deciding the install is already satisfied
(`claude_code.py:451-463`, `codex.py:402-414`). `hermes`, `pi`, `opencode` and
`gemini_cli` have no such check; when a version is pinned, `_version` keeps the
pin and `version()` reports it, because the base probes only when `_version is
None` (`base.py:1093-1100`). `OmpAgent` takes a third position: it forces
`self._version = None` so the probe always runs and the pin is never reported as
a version (`omp_agent.py:258-265`).

### Error classification — 0 of 6 declare `ERROR_PATTERNS`; 2 override `_classify_exec_error`

Grep for `ERROR_PATTERNS` across the six returns nothing, so all six use the
base's default patterns (`base.py:487`). `claude_code` (`claude_code.py:427-449`)
and `codex` (`codex.py:386-400`) override `_classify_exec_error` to strip
model-authored text out of the evidence before classification — a
JSONL-aware refinement the other four do not need, because their harness errors
are not mixed into a stream of model text the same way. `OmpAgent` does neither;
it adds an explicit post-run guard instead (`omp_agent.py:675-727`).

### Instruction delivery — env var 2, positional 3, `--prompt=` 1

`claude_code.py:1944-1955` and `hermes.py:473,517` pass the instruction through an
environment variable (both cite shell-escaping safety). `pi.py:456`,
`codex.py:1774` and `opencode.py:624` pass a `shlex.quote`d positional argument.
`gemini_cli.py:987` uses `--prompt=`. `OmpAgent` passes a positional argument,
quoted at the argv level (`omp_agent.py:736-768`).

### Declared-but-uncompiled flags — 1 of 6

`hermes` declares two `Cli()` annotations (`--toolsets` and `--max-turns`,
`hermes.py:49-56`) but `run()` never calls `build_cli_flags()`. `--toolsets` is
hand-rendered (`hermes.py:525`) and `max_turns` is written into
`config.yaml` (`hermes.py:470`) instead. The other five compile their annotations
through `build_cli_flags()`. This is a factual observation, not a claim that
`--max-turns` is broken: the flag is simply never produced by the declarative
path.

### Setup timeout — 1 of 6 overrides it

`hermes.py:97` sets `DEFAULT_SETUP_TIMEOUT_SEC = 1200.0` against the base's 360 s
(`../base.py:59`), with a comment recording that the default aborted 8 of 21 trials
in a 5-wide run. The other five and `OmpAgent` take the default.

## Question 1: how config reaches the container

**Verdict.** Six of six build config in-container from options and derived values.
**Two of six also accept a native config source — `claude_code` and `codex` — and
both use Harbor's `config_source` for exactly one thing: a single native config
file (a host `Path` or an inline dict), rendered and uploaded to one path.** No
agent in the package ships a directory. `OmpAgent`'s `_ship_config()` is therefore
a genuine departure in shape, while the *name* `config_source` is established
convention with a different meaning.

**Which shape each of the six uses.**

| agent | shape | citation |
|---|---|---|
| `claude_code` | (a) in-container from options, **plus** a native settings JSON from `config_source`, uploaded to `/tmp/claude-code-settings/settings.json` and passed as `--settings <path>`, removed in a `finally` | `claude_code.py:377-397` (load+validate), `claude_code.py:1897-1904` (mkdir), `1924-1928` (`--settings`), `1964-1975` (cleanup) |
| `codex` | (a) in-container from options, **plus** a native TOML from `config_source` as the base, with `openai_base_url` and task MCP servers merged on top, uploaded to `$CODEX_HOME/config.toml` | `codex.py:1536-1569` (load+validate), `1569-1610` (merge), `1611-1624` (render+upload), `1733-1734` (call site) |
| `hermes` | (a) only: a generated `config.yaml` written by heredoc, with MCP appended | `hermes.py:135-168`, `472-478` |
| `pi` | (a) only: `models.json` for a custom endpoint, `mcp.json`, and a generated `max-turns.ts` extension, all under an isolated config dir | `pi.py:212-343` |
| `opencode` | (a) only: one `opencode.json` written by `echo`, layering defaults → auto-generated → job overlay | `opencode.py:521-575` |
| `gemini_cli` | (a) only: `settings.json` with MCP servers, model aliases, tool exclusions and `experimental.skills` | `gemini_cli.py:764-833` |

**Does any of the six use `config_source`? Verified yes — 2 of 6.**

- `claude_code`: 11 references. `_load_base_settings` reads `self.config_source`
  and accepts either a `dict` or a `Path` (`claude_code.py:379-396`), rejecting a
  non-object (`claude_code.py:392-396`); `_upload_base_settings` returns early
  when it is `None` (`claude_code.py:401-402`); `run()` gates the `--settings`
  flag and the staging-dir mkdir on it (`claude_code.py:1905-1908,1924-1928`) and
  removes the staging dir in a `finally` (`claude_code.py:1964-1975`).
- `codex`: 9 references. `_load_base_config` accepts a `dict` (round-tripped
  through TOML to prove it is TOML-representable, `codex.py:1541-1554`) or a
  `Path` (`codex.py:1556-1566`), and `__init__` calls it eagerly
  (`codex.py:153`).
- The other four: **zero** references. Absence is a finding — `hermes`, `pi`,
  `opencode` and `gemini_cli` accept no native config file at all, and their
  `capabilities.native_config` is false, so Harbor's `config=` kwarg raises for
  them (`base.py:620`).

**Is `config_source` a convention, or is a directory ship?** Widening the grep to
the whole package settles it:

- Harbor's `config_source` property is used by **6 of 38** installed agents:
  `claude_code.py`, `codex.py`, `deerflow.py:463-472`, `junie.py:451-457`,
  `muse_code.py:95-99`, `swe_agent.py` (a local variable name only, `swe_agent.py:574`).
  Every one treats it as **a single config file (`Path`) or an inline dict** —
  `deerflow.py:464-472` (`yaml.safe_load` of one file), `junie.py:452-456`
  (`json.loads` of one file), `muse_code.py:95-99` (`json.loads` of one file).
  The `native_config=True` set is exactly `claude_code`, `codex`, `deerflow`,
  `junie`, `muse_code` — five modules.
- **Zero** modules ship a host directory: grep for
  `git archive|archive_git_head|tarfile` across all 51 `.py` files returns no
  files. There is
  no precedent in the package for archiving a checkout and extracting it in the
  container.

**Where `OmpAgent` sits, cited on both sides.**

- *Conforming*: it accepts config from the caller as an option and does not read
  the environment or a benchmark for it — the same posture as every other option
  on `OmpOptions` (`options.py:62-241`). It also names the option
  `config_source` (`options.py:135`), which is the established name.
- *Departing*: `OmpOptions.config_source` is a `str | None` field naming **a HOST
  git checkout directory** (`options.py:159-169`), paired with `config_paths` as
  `git archive` pathspecs (`options.py:170-179`). `_ship_config` verifies the tree
  is clean and archives HEAD restricted to those pathspecs (`omp_agent.py:364-402`,
  via `archive_git_head` `omp_agent.py:98-181`), uploads the tar
  (`omp_agent.py:396-402`) and extracts it into the config dir after the home
  reset (`omp_agent.py:548-563`). Two further facts sharpen the departure:
  1. It is a **different object** from Harbor's `config_source`. `OmpAgent` does
     not declare `native_config` (`omp_agent.py:243-250`), so Harbor's `config=`
     kwarg raises for it (`base.py:620`) and the base property is never the
     `OmpOptions` field. The name collides; the mechanism does not.
  2. The **`config_source` name is also already claimed by the harness's own
     install-time jargon** in this repo's docs: `omp_agent.py:33` says "no native
     `config=` (consumer config travels through `seed`/`config_source`)" — so
     inside `harbor_omp` the word means the directory ship, while everywhere else
     in Harbor it means one native file. That is a reader hazard worth resolving
     when the config path changes.

**So:** shipping a directory is an `OmpAgent` departure with no precedent among
the 38 installed agents. Accepting a native config source is not a departure at
all — 6 of 38 do it, 2 of them among the six compared here. The reusable part of
the convention is the *accessor discipline* those six follow: read the source
once, validate it eagerly, refuse an unrenderable value, and skip the upload when
it is unset (`claude_code.py:379-403`, `codex.py:1536-1566`).

## Question 2: how the API key is declared

**Verdict.** There is no single convention. Of the six, **2 declare a static
class-level `api_key_envs=(...)` tuple** (`claude_code`, `gemini_cli`), **1
derives the env name from the resolved connection** (`pi`), **1 relies on the
provider table's default** (`codex`), and **2 declare no API key at all**
(`opencode`, `hermes`). `OmpAgent` is in the no-declaration camp. If `OmpAgent`
must pick one, the static tuple is the plurality (7 of 38 in the package, 2 of 6
here) and the derived helper has one in-package precedent outside the six.

**Shape A — static class-level tuple on `MODEL_CONNECTION`.**

```python
MODEL_CONNECTION = ModelConnectionSpec(
    default_provider="anthropic",
    api_key_envs=("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
    base_url_envs=("ANTHROPIC_BASE_URL",),
)
```

- `claude_code.py:124-128` — two names, tried in order.
- `gemini_cli.py:93-97` — one name, plus `passthrough=True`.

Semantics, from the resolver: the spec's `api_key_envs` are tried **before** the
provider table's (`../model_connection.py:207-212`), and with
`passthrough=False` the resolved value is written back under
`spec.api_key_envs[0]` (`../model_connection.py:229-233`). The `ModelConnectionSpec`
docstring names the users: "claude-code, gemini-cli, openhands, mini-swe-agent"
(`../model_connection.py:158-166`). Widened to the package, the static-tuple camp
is `claude_code.py:126`, `gemini_cli.py:95`, `code_puppy.py:115`, `fx.py:53`,
`mini_swe_agent.py:509`, `muse_code.py:77`, `openhands.py:106` — **7 of 38**.

A near-camp: `codex.py:132` declares `ModelConnectionSpec(default_provider="openai")`
with **no** `api_key_envs`, so the key comes from the provider table entry
`"openai": ProviderAccess(("OPENAI_API_KEY",), …)` (`../model_connection.py:100-104`).
Declaratively this is the same thing as a static tuple; it is just spelled with
the table. `codex` then consumes `access.api_key` directly
(`codex.py:1718`).

**Shape B — derived `_api_key_env_name(access) -> str | None`.**

```python
@staticmethod
def _api_key_env_name(access: ResolvedModelConnection) -> str | None:
    if access.api_key is None:
        return None
    return next(
        (name for name, value in sorted(access.env.items()) if value == access.api_key),
        None,
    )
```

- `pi.py:200-209`. It is called from `_build_custom_models_json`
  (`pi.py:227`), which raises when the name is `None` (`pi.py:228-231`) and
  otherwise writes `"apiKey": f"${api_key_env}"` into `models.json`
  (`pi.py:241-250`). The point is that Pi's own config needs the **name** of the
  env var, not its value, so `pi` recovers the name by matching values inside the
  passthrough `access.env`.

There is one other `_api_key_env_name` in the package, with a different
signature: `mcode.py:164` is a static function taking `(provider, env)`. So the
derived shape has **2 of 38** implementations, **1 of 6** here.

**Shape C — no API key declaration.**

- `opencode.py:79` declares `ModelConnectionSpec(passthrough=True)` and never
  mentions a key env; `run()` just exports `dict(self.model_connection.env)`
  (`opencode.py:593`).
- `hermes` declares no `MODEL_CONNECTION` at all (`hermes.py:61-66`) and
  hard-codes its own provider→env-name map:

  ```python
  _NATIVE_PROVIDERS: dict[str, tuple[str | None, list[str]]] = {
      "anthropic": ("anthropic", ["ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN"]),
      "openai": ("openai-api", ["OPENAI_API_KEY"]),
      "zai": ("zai", ["GLM_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY"]),
      "kimi": ("kimi-coding", ["KIMI_API_KEY"]),
      "minimax": ("minimax", ["MINIMAX_API_KEY"]),
      "minimax-cn": ("minimax-cn", ["MINIMAX_CN_API_KEY"]),
  }
  ```

  `hermes.py:38-45`, consumed by a loop over `os.environ` at `hermes.py:440-448`,
  with an OpenRouter fallback at `hermes.py:455-465`. This duplicates a
  `MODEL_CONNECTION` spec by hand — a shape no other agent in the six uses, and
  the one case where a key is read from `os.environ` directly rather than through
  `_get_env`/`model_connection`.

**Where `OmpAgent` sits.** `MODEL_CONNECTION = ModelConnectionSpec(passthrough=True)`
(`omp_agent.py:251`), and the module contains **no** reference to `api_key` at all.
It exports `dict(self.model_connection.env)` as the run environment
(`omp_agent.py:589,595`), which is exactly `opencode`'s shape
(`opencode.py:79,593`) and half of `pi`'s (`pi.py:98`, which then adds the derived
name lookup because Pi's config file needs it). So `OmpAgent` conforms to Shape C,
and conforms to the pass-through posture that 4 of the six-plus-omp declare
(`pi.py:98`, `opencode.py:79`, `gemini_cli.py:97`, `omp_agent.py:251`).

**If `OmpAgent` must pick one:** the static tuple. Reasons, each grounded:
it is what the two agents whose CLIs take an explicit env-var name do
(`claude_code.py:126`, `gemini_cli.py:95`); it is the plurality in the package
(7 of 38); it keeps the name visible at class scope instead of deriving it by
value-matching; and it needs no change to `passthrough=True`, which omp needs
because omp reads its own provider env names. The derived helper
(`pi.py:200`) exists only because Pi's `models.json` must contain the *name* of a
key it does not own — a constraint `OmpAgent` does not currently have.

## Install and version conventions

**Install styles observed.**

| style | agents | citation |
|---|---|---|
| npm global, nvm-sourced Node | `pi`, `gemini_cli` | `pi.py:191-196`, `gemini_cli.py:172-179` |
| npm global, musl-aware (apk Node on musl, nvm otherwise) | `codex`, `opencode` | `codex.py:426-441`, `opencode.py:143-152` |
| npm **or** curl bootstrap script, chosen by package manager | `claude_code` | `claude_code.py:477-489` |
| curl install script from GitHub raw (clones + uv-resolves the toolchain) | `hermes` | `hermes.py:117-128` |
| bun global | `OmpAgent` | `install.py:61-65` |

Common to all: an `ensure_system_dependencies` call before the install
(`claude_code.py:473`, `codex.py:422`, `hermes.py:114`, `pi.py:178`,
`opencode.py:134`, `gemini_cli.py:171`), the install running as the agent user
via `exec_as_agent` (every citation above), and the install command ending by
printing the version — `claude --version` (`claude_code.py:489`),
`codex --version` (`codex.py:441`), `hermes version` (`hermes.py:126`),
`pi --version` (`pi.py:195`), `opencode --version` (`opencode.py:150`),
`gemini --version` (`gemini_cli.py:192`), `omp --version` (`install.py:64`).
`OmpAgent` follows all three, including the trailing version print.

Two agents add an idempotence check the others lack: `claude_code`
(`claude_code.py:451-463`) and `codex` (`codex.py:402-414`) probe the installed CLI
first and skip the install when the requested version is already present.
`hermes` is the only one that overrides the setup timeout (`hermes.py:97`).

**The pin-vs-report split.** All six splice a caller-supplied version into the
install command, and all six have a `get_version_command`. The split is what the
*reported* version means:

- **Verified** (2 of 6): `claude_code` and `codex` compare the measured version
  to the requested one and treat a mismatch as "not satisfied", so the pin and the
  report are reconciled (`claude_code.py:451-463`, `codex.py:402-414`).
- **Reported as pinned** (4 of 6): `hermes`, `pi`, `opencode` and `gemini_cli`
  set `_version` from the option, and the base probes only when `_version is None`
  (`base.py:1093-1100`), so with a pin the reported version is the pin. `hermes`
  even re-asserts this by overriding `version()` to return `self._version`
  (`hermes.py:105-106`).
- **Always measured** (1 of 1 in its own camp): `OmpAgent` sets
  `self._version = None` in `__init__` precisely so the probe always runs, with a
  comment stating that Harbor reads `options.version` as the reported version too
  and the pin must never be claimed as verified (`omp_agent.py:258-265`). The
  docstring says the same (`omp_agent.py:233-235`), and the pin travels to the
  install command through `package_spec(self.options.version)`
  (`omp_agent.py:293`, `options.py:38-48`).

`hermes`'s pin is also the odd one out in kind: it is passed as `--branch <value>`
(`hermes.py:117`), a git branch on the install script, not a package version — so
"the version" for Hermes selects a branch of a checkout.

## OmpAgent conformance and departures

**Conforms.**

| dimension | OmpAgent | follows |
|---|---|---|
| options model as the only input surface | `omp_agent.py:253`, `options.py:62-241` | 6 of 6 |
| `capabilities` with atif/resume/skills/mcp_servers | `omp_agent.py:243-250` | 6 of 6 |
| zero `CLI_FLAGS`/`ENV_VARS`, zero `Cli()`/`Env()` | grep: none in `options.py`; base forbids mixing `base.py:585-592` | 6 of 6 |
| `ensure_system_dependencies` before install | `omp_agent.py:301`, `install.py:26` | 6 of 6 |
| version spliced into the install command | `omp_agent.py:293`, `options.py:38-48` | 6 of 6 |
| `get_version_command` / `parse_version` | `omp_agent.py:278-283`, `install.py:71-81` | 6 of 6 |
| `populate_context_post_run` | `omp_agent.py:770` | 6 of 6 |
| MCP built in-container from `self.mcp_servers` | `omp_agent.py:522-546` | 6 of 6 |
| `@with_prompt_template` on `run()` | `omp_agent.py:566` | 6 of 6 |
| `ModelConnectionSpec(passthrough=True)` | `omp_agent.py:251` | `pi.py:98`, `opencode.py:79`, `gemini_cli.py:97` |
| `--continue` for resume | `omp_agent.py:756-757` | `claude_code.py:1929`, `pi.py:429`, `opencode.py:614` |
| `_seed_load_trajectory` called from `run()` | `omp_agent.py:574-575` | `claude_code.py:1938`, `codex.py:1701` |
| handoff classmethod shape | `omp_agent.py:894-928` | `claude_code.py:202-226` |
| `convert_trajectory` override | `omp_agent.py:826` | `claude_code.py:606`, `codex.py:573` |
| `remote_session_logs_dir` override | `omp_agent.py:884` | `claude_code.py:602`, `codex.py:569` |
| fails before model spend on bad input | `omp_agent.py:115-118,289-300,404-422` | 6 of 6 (each in its own way) |

**Departs.**

1. **Directory ship from a host checkout.** `_ship_config` (`omp_agent.py:364-402`)
   archives a git checkout with `git archive` (`omp_agent.py:98-181`) and extracts
   it in-container (`omp_agent.py:548-563`). No precedent: 0 of 38 installed
   modules use `git archive`/`tarfile`. The two `config_source` users among the six
   take a single file (`claude_code.py:379-396`, `codex.py:1556-1566`).
2. **`config_source` is an options field, not Harbor's property.** `OmpAgent`
   declares no `native_config` (`omp_agent.py:243-250`), so the base property
   (`base.py:684-687`) is unreachable for it and the `config=` kwarg raises
   (`base.py:620`). The name is reused with a different meaning
   (`options.py:159-169`), which is a reader hazard against `omp_agent.py:33`.
3. **No `_build_register_skills_command`.** All six have that method
   (`claude_code.py:1688`, `codex.py:1526`, `hermes.py:190`, `pi.py:345`,
   `opencode.py:511`, `gemini_cli.py:743`); `OmpAgent` inlines the copy into
   `_config_home_command` (`omp_agent.py:511-520`). The behaviour is the same; the
   named seam is missing, so a caller cannot ask the agent to render its skills
   step.
4. **No `_ensure_config_dir`-equivalent named step.** Only `pi` has
   `_ensure_config_dir` (`pi.py:270-275`) and no other module in the package has
   one, so this is not a departure from a convention — but `OmpAgent`'s config-dir
   work is spread across `_config_home_command` and `_config_extract_command`
   (`omp_agent.py:481-563`) with no single "the config dir is ready" step, whereas
   `pi` and `claude_code` each have one place that creates it
   (`pi.py:270-275`, `claude_code.py:1897-1904`).
5. **Always-measured version.** `omp_agent.py:258-265` against 4 of 6 that report
   the pin and 2 of 6 that verify it. This is a deliberate improvement, not an
   error — but it means `version()` and `options.version` disagree by design, and
   a consumer that reads the option as the version will be wrong.
6. **A post-run failure path the six do not have.** The no-op guard
   (`omp_agent.py:675-727`) fails a run after model spend when the session records
   no tool call. `opencode` has a post-spend failure too
   (`opencode.py:632-634`), so the pattern exists, but the guard's purpose — a
   model that answers without acting being scored as a failure rather than a
   verdict — is unique to this agent.
7. **Extension points as options.** `plugin`, `seed`, `extra_files`,
   `pre_commands`, `post_commands` (`options.py:180-241`). The nearest analogues
   are `opencode_config` (`opencode.py:45-47`, a deep-merged dict) and
   `claude_code`'s `memory_dir` (`claude_code.py:107-109`, a host dir copied in) —
   both narrower. `extra_files` is the closest thing in the six to shipping host
   content, and it is one file per pair (`omp_agent.py:404-422`), not a directory.
8. **No ACP bridge.** `omp_agent.py:224` (no `ACPAgentMixin`, no `bridges`
   capability) — with `hermes` and `pi`, against 4 of 6.
9. **Zero `Cli()`/`Env()` annotations, so `build_cli_flags()` is never called.**
   `OmpAgent` builds argv as a list (`omp_agent.py:736-768`) and records it
   (`omp_agent.py:579`). This is the *same outcome* as `hermes`
   (`hermes.py:503-533`, which declares two annotations and compiles neither) but
   a different cause: `OmpAgent` declares none, so there is nothing to compile.
   `run_flags` is the deliberate replacement — verbatim, ordered, and recorded.

## What OmpAgent should copy, and from whom

1. **Read the config source once, validate it eagerly, and refuse an
   unrenderable value — from `codex` and `claude_code`.** `codex` loads at
   construction (`codex.py:153`) and validates through a TOML round-trip before
   accepting an inline dict (`codex.py:1541-1554`), naming the file in the error
   (`codex.py:1557-1566`); `claude_code` does the same for JSON
   (`claude_code.py:176,379-400`). `OmpAgent` already validates eagerly
   (`omp_agent.py:360-402`) but does it inside `install()`; moving the
   *validation* earlier — leaving the upload in `install()` — would match both
   agents and fail a misconfiguration at construction rather than at setup.
2. **Keep the `None`-means-unset early return on every config writer — from
   `claude_code` and `codex`.** `_upload_base_settings` returns immediately when
   `config_source` is `None` (`claude_code.py:401-402`) and `_upload_effective_config`
   returns when the merged config is empty (`codex.py:1618-1619`).
   `OmpAgent` gates its ship on `is not None` (`omp_agent.py:298-299,448-449`) and
   its extract likewise (`omp_agent.py:548-549`), so it conforms — the copy is
   *why*: an unset config must never produce an empty upload.
3. **Adopt the `_build_register_skills_command` seam — from any of the six, most
   directly from `codex` or `pi`.** `codex.py:1526-1536` and `pi.py:345-353` both
   register into `$HOME/.agents/skills` with the identical `mkdir -p` +
   `cp -r … 2>/dev/null || true` shape; `claude_code.py:1688-1700` uses its own
   config dir. All six guard on `if not self.skills_dir: return None` and return a
   shell string. `OmpAgent`'s target differs (`<config_dir>/agent/skills`,
   `omp_agent.py:511-520`) and must stay different, but the *method* is worth
   having: it is the one dimension where all six agree on a name, and it makes the
   skills step independently checkable.
4. **If a static API-key env name is declared, declare it on `MODEL_CONNECTION`
   as `api_key_envs=(...)` — from `claude_code` and `gemini_cli`.** Two names in
   order is the shape with a reason behind it (`claude_code.py:124-128`, where
   `ANTHROPIC_AUTH_TOKEN` is the fallback name); one name is enough where there is
   only one (`gemini_cli.py:95`). Do not take `hermes`'s hand-rolled
   `_NATIVE_PROVIDERS` map (`hermes.py:38-45`): it duplicates the provider table
   (`../model_connection.py:15-119`) and reads `os.environ` directly instead of
   through `_get_env` (`hermes.py:440-448`), which loses `extra_env` precedence
   (`base.py:676-683`).
5. **Keep the always-measured version — and cite `hermes` as the counter-example.**
   `hermes` overrides `version()` to return the pin-filled `self._version`
   (`hermes.py:105-106`) and the base probes only when it is `None`
   (`base.py:1093-1100`), so a pinned Hermes reports a version nobody measured.
   `OmpAgent`'s `self._version = None` (`omp_agent.py:258-265`) is the right
   choice; `claude_code` and `codex` show the stronger version of it — verify the
   measurement against the request (`claude_code.py:451-463`, `codex.py:402-414`),
   which `OmpAgent` does not do.
6. **Follow `claude_code`'s handoff destination logic, not its resume contract.**
   `claude_code` resolves the local config dir from an env override with a
   documented default (`CLAUDE_CONFIG_DIR` or `~/.claude`, `claude_code.py:220-222`)
   and slugs the project dir (`claude_code.py:223`). `OmpAgent` already does the
   equivalent (`PI_CONFIG_DIR` or `.omp`, `omp_agent.py:921-923`) and returns
   `["omp", "--resume", <stem>]` (`omp_agent.py:926`) exactly as `claude_code`
   returns `["claude", "--resume", session.stem]` (`claude_code.py:226`). Copy the
   *precedent*, not the code: no change needed, and the citation is what keeps it
   from being refactored away later.
7. **Take `hermes`'s setup-timeout override only if the install is measurably
   long.** `hermes.py:97` sets 1200 s against the base's 360 s (`../base.py:59`) and
   its comment (`hermes.py:94-96`) records the evidence (8 of 21 trials aborted).
   No other agent overrides it. `OmpAgent` should leave the default until a bun
   install is measured to exceed it — and if it does, the override should carry the
   same kind of measured note.
8. **Do not copy `opencode`'s or `hermes`'s post-spend failure as a substitute for
   a pre-spend gate.** `opencode` raises after the run on error events
   (`opencode.py:632-634`) and `OmpAgent`'s no-op guard is likewise post-spend
   (`omp_agent.py:675-727`). Both are legitimate, but the six's stronger habit is
   the pre-spend abort: `pi` refuses an out-of-range version *before* installing
   (`pi.py:143-177`), `hermes` refuses before launching when no key resolves
   (`hermes.py:455-464`), and `codex`/`claude_code` validate config at
   construction (`codex.py:153`, `claude_code.py:176`). `OmpAgent` should keep its
   pre-spend aborts (`omp_agent.py:115-118`) and treat the guard as a last resort,
   not the primary gate.

## Could not verify

- **That any install command resolves against its registry or network.** No
  install was run; every install claim is the command text at the cited line.
- **That the reported version string parses in practice.** `parse_version`
  behaviour is read, not exercised against real CLI output.
- **That `hermes`'s `--max-turns` annotation is intentionally inert.** The fact is
  verified — `run()` never calls `build_cli_flags()` (`hermes.py:417-540`) while
  the annotation exists (`hermes.py:52`) — but the intent is not stated in the
  file, so it may be a defect rather than a choice. `[INFERENCE]` if treated as
  deliberate.
- **Whether the other 32 installed agents use a directory ship in some way the
  grep missed.** The grep covered `git archive|archive_git_head|tarfile` over all
  51 `.py` files in `installed/`; a ship built with `subprocess`, `zipfile`, or a
  non-git copy would not match. The six compared here were read directly, so the
  verdict for the six is firm; the package-wide "0 of 38" carries that caveat.
- **Whether `OmpOptions.config_source`'s name collision with Harbor's
  `config_source` property is a known, accepted choice.** The code shows the
  collision (`options.py:135` vs `base.py:684-687`) and the docstring at
  `omp_agent.py:33` shows the repo already uses the word for the directory ship.
  No decision record was read.
- **Harbor's own documentation of these agents.** Only the source was read;
  no `harbor` docs, changelog or upstream README was consulted, so a documented
  convention that the code violates would not have been caught here.
- **The behaviour of `sync_trajectory` against any of these agents.** Nothing was
  run.
