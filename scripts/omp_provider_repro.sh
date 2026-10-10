#!/usr/bin/env bash
# Reproduce the idle-greeting no-op with the real omp, pinned per OpenRouter
# upstream. Runs INSIDE a benchmark image (needs network + OPENROUTER_API_KEY).
#
#   docker run --rm -e OPENROUTER_API_KEY -v "$PWD/scripts:/repro:ro" \
#     -v /path/to/instruction.md:/repro-in/instruction.md:ro \
#     <image> bash /repro/omp_provider_repro.sh "OpenInference Venice" 3
#
# Every cell runs the exact argv harbor_omp records (run-flags.json), under an
# isolated HOME seeded like the fast-30 profile, plus a models.yml that pins
# deepseek/deepseek-v4-flash to ONE OpenRouter upstream (openRouterRouting.only).
# A run is GREET when omp's session holds exactly one assistant message, it
# ended with stopReason "stop", and it made no tool call. Exit 1 if any GREET.
#
# Add `-e PI_OPENROUTER_RESPONSES=0` to the docker run to use Chat Completions
# instead of the Responses API. Recorded 2026-10-10 on omp/18.6.0: OpenInference
# greeted on BOTH wires (Responses 6/6 incl. 3 nonce-busted; Chat 3/3 — an
# earlier Chat pass that day read 0/3 but kept no gen ids); Venice engaged, 0/3.
# The host is the variable, not the wire.
set -uo pipefail
providers=${1:-"OpenInference Venice"}
n=${2:-3}
nonce_cell=${3:-1}   # 1 = also run OpenInference with a cache-busting nonce
instr=/repro-in/instruction.md

apt-get update -qq >/dev/null && apt-get install -y -qq curl git unzip >/dev/null
curl -fsSL https://bun.sh/install | bash >/dev/null 2>&1
export PATH="$HOME/.bun/bin:$PATH"
bun install -g --ignore-scripts @oh-my-pi/pi-coding-agent@18.6.0 >/dev/null 2>&1
echo "omp: $(omp --version)"

run_cell() { # $1 provider  $2 label  $3 prefix
  local provider=$1 label=$2 prefix=$3 home sess
  home=$(mktemp -d /tmp/omp-home.XXXX); sess=$home/sessions
  mkdir -p "$home/.omp/agent/agents"
  cat >"$home/.omp/agent/config.yml" <<'YML'
dev:
  autoqa: false
marketplace:
  autoUpdate: "off"
modelRoles:
  main: "deepseek/deepseek-v4-flash:high"
  plan: "deepseek/deepseek-v4-flash:max"
  task: "glm-5.3-flash:auto"
task:
  agentAdvisor: {}
  enableEffort: false
  maxRecursionDepth: 2
YML
  printf -- '---\nname: task\ndescription: Agent override pinned by the eval profile\nspawns: scout, reviewer\n---\n\nAgent override pinned by the eval profile. Spawns restricted to scout, reviewer.\n' \
    >"$home/.omp/agent/agents/task.md"
  cat >"$home/.omp/agent/models.yml" <<YML
providers:
  openrouter:
    modelOverrides:
      deepseek/deepseek-v4-flash:
        compat:
          openRouterRouting:
            only: [$provider]
YML
  (cd /app && HOME=$home PI_CONFIG_DIR=.omp timeout 90 omp -p --auto-approve \
      --no-extensions --no-skills --no-rules --session-dir="$sess" \
      --model=openrouter/deepseek/deepseek-v4-flash --thinking=high \
      "${prefix}$(cat "$instr")" >"$home/out.txt" 2>&1)
  python3 - "$sess" "$label" "$home/out.txt" <<'PY'
import glob, json, sys
sess, label, out = sys.argv[1:4]
msgs = []
for f in glob.glob(sess + "/*.jsonl"):
    for line in open(f):
        o = json.loads(line)
        m = o.get("message") or {}
        if o.get("type") == "message" and m.get("role") == "assistant":
            msgs.append(m)
if not msgs:
    print(f"{label:28} NO-CALL  {open(out).read()[:100]!r}")
    sys.exit(0)
first = msgs[0]
tools = any(c.get("type") == "toolCall" for c in first.get("content", []))
text = "".join(c.get("text", "") for c in first.get("content", []) if c.get("type") == "text")
greet = len(msgs) == 1 and first.get("stopReason") == "stop" and not tools
u = first.get("usage", {})
print(f"{label:28} {'GREET' if greet else 'engaged':8} turns={len(msgs):<3} "
      f"cacheRead={u.get('cacheRead')} gen={first.get('responseId')} "
      f"{text[:60]!r}")
open("/tmp/greets", "a").write("1\n" if greet else "")
PY
}

: >/tmp/greets
for p in $providers; do
  for i in $(seq 1 "$n"); do run_cell "$p" "$p #$i" ""; done
done
if [ "$nonce_cell" = 1 ]; then
  for i in $(seq 1 "$n"); do
    run_cell OpenInference "OpenInference+nonce #$i" "[run $RANDOM$RANDOM] "
  done
fi
g=$(wc -l </tmp/greets)
echo "GREET runs: $g"
[ "$g" -eq 0 ]
