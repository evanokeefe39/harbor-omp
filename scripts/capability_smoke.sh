#!/usr/bin/env bash
# Container smoke for the capability closers, run INSIDE the benchmark image
# with the real omp 18.6.0. Every omp cell is wrapped in `timeout` and labelled,
# so a stall names itself instead of hanging the run (the first cut of this
# script hung for 3 hours with no timeout — see DEFECTS).
#
#   docker run --rm -e OPENROUTER_API_KEY -v <dir>:/smoke:ro \
#     --entrypoint bash <image> /smoke/capability_smoke.sh 2>&1 | tee /smoke/out.log
#
# Proves, on the exact files the agent writes / argv it passes:
#   D6 skills : {agent_dir}/skills/pdf/SKILL.md  -> omp read skill://pdf
#   D3 resume : omp --continue in a --session-dir continues the thread
#   D4 load   : omp --resume <stem> accepts a session seeded as a file
#   D7 mcp    : {agent_dir}/mcp.json -> omp read mcp://probe://hello, and a
#               configured server does not stall a plain run
set -uo pipefail
apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq curl unzip >/dev/null 2>&1
curl -fsSL https://bun.sh/install | bash >/dev/null 2>&1
export PATH="$HOME/.bun/bin:$PATH"
bun install -g --ignore-scripts @oh-my-pi/pi-coding-agent@18.6.0 >/dev/null 2>&1
echo "omp: $(omp --version)"
agent_dir="$HOME/.omp/agent"
model=openrouter/deepseek/deepseek-v4-flash
base=(omp -p --auto-approve --no-extensions --no-rules --session-dir)
cell() { # $1 label, rest: command
  local label=$1; shift
  "$@" >"/tmp/$label.out" 2>&1
  local rc=$?
  echo "CELL $label rc=$rc :: $(tail -c 200 "/tmp/$label.out" | tr '\n' ' ')"
}

# --- baseline: no skills, no mcp ------------------------------------------
cell base-no-skills timeout 90 "${base[@]}" /tmp/c1 --no-skills \
  --model="$model" "Reply with the single word PELICAN."

# --- D6: skills, same layout the agent writes ------------------------------
mkdir -p "$agent_dir/skills/pdf"
cat >"$agent_dir/skills/pdf/SKILL.md" <<'MD'
---
name: pdf
description: Smoke probe skill for the capability closers
---

PROBE-SKILL-BODY
MD
cell d6-read-skill timeout 60 omp read skill://pdf
cell d6-run-skill timeout 90 "${base[@]}" /tmp/c2 \
  --model="$model" "Reply with the single word PELICAN."

# --- D3: --continue in a --session-dir continues the thread -----------------
cell d3-turn1 timeout 90 "${base[@]}" /tmp/c3 \
  --model="$model" "Remember the codeword BANANA. Reply OK."
cell d3-turn2 timeout 90 "${base[@]}" /tmp/c3 --continue \
  --model="$model" "What was the codeword? Reply with just the word."

# --- D4: --resume <stem> accepts the seeded session file --------------------
stem=$(basename "$(ls /tmp/c3/*.jsonl 2>/dev/null | head -1)" .jsonl)
mkdir -p /tmp/seed && cp /tmp/c3/*.jsonl /tmp/seed/ 2>/dev/null
cell d4-load timeout 90 "${base[@]}" /tmp/seed --resume "$stem" \
  --model="$model" "What was the codeword? Reply with just the word."

# --- D7: mcp.json, same file the agent writes -------------------------------
python3 - "$agent_dir" <<'PY'
import json, sys
json.dump(
    {"mcpServers": {"probe": {"type": "stdio", "command": "python3",
                              "args": ["/smoke/mcp_probe_server.py"]}}},
    open(sys.argv[1] + "/mcp.json", "w"),
)
PY
cell d7-read-mcp timeout 60 omp read mcp://probe://hello
cell d7-run-with-mcp timeout 90 "${base[@]}" /tmp/c4 --no-skills \
  --model="$model" "Reply with the single word PELICAN."
echo done
