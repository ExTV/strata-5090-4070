#!/usr/bin/env bash
# Qwen3.8-Flash-Next (ISTA GSQ-RCO IQ3_XXS) at 262,144 tokens on an RTX 5090 + RTX 4070 Ti SUPER, served by the
# patched Strata on :8888 (OpenAI and Anthropic compatible, model name qwen3.8-flash-next, images on).
# Layers 0-35 on the 5090, 36-47 and the drafter on the 4070; prompts read on the 5090 only (--prefill-main);
# the experts neither card holds sit in a page-locked RAM copy (--resident-experts, ~7 GB) and the two cards
# overlap decode windows (the fork's --pipeline-windows, on by default); switching between conversations
# restores a parked one in under a second (--conversation-cache-mib, 4 GB: one 130K-token session, not two).
# Knobs: CONFIG= another config in strata/, PORT=, HOST= (default 127.0.0.1; the server has no authentication, so
# HOST=0.0.0.0 exposes an unauthenticated 262K-context endpoint with image input to the whole LAN; put it behind
# a reverse proxy or a firewall rule if you do that).  Measured numbers: docs/benchmarks.md.
set -euo pipefail
cd "$(dirname "$0")/../strata"
CONFIG=${CONFIG:-strata-flash-next-262k.json}
PORT=${PORT:-8888}
HOST=${HOST:-127.0.0.1}
[ -f "$CONFIG" ] || { echo "missing $CONFIG: run ./install.sh first" >&2; exit 1; }
[ -f packs/gsq-iq3_xxs/dense.bin ] && [ -f mtp/rt/experts.bin ] || { echo "run ./prepare.sh first" >&2; exit 1; }
ss -ltn | grep -q ":$PORT " && { echo "port $PORT is already listening" >&2; exit 1; }
pgrep -x strata >/dev/null && { echo "a strata engine is already running" >&2; exit 1; }
exec .venv/bin/python -m serve.server --engine strata --config "$CONFIG" --host "$HOST" --port "$PORT"
