#!/usr/bin/env bash
# Qwen3.8-Flash-Next (ISTA GSQ-RCO IQ3_S, the shipped config; CONFIG=strata-flash-next-iq3xxs-262k.json for IQ3_XXS)
# at 262,144 tokens on an RTX 5090 + RTX 4070 Ti SUPER, served by the patched Strata on :8888 (OpenAI and Anthropic
# compatible, model name qwen3.8-flash-next, images on).
# Layers 0-38 on the 5090, 39-47, the drafter and the image encoder on the 4070; prompts read on the 5090
# (--prefill-main), the parts up to the whole context split-wise so each card runs its own layers
# (--prefill-main-small); the draft layer's K/V computed there too (STRATA_PM_MTP_BATCH=1); the experts neither card
# holds sit in a page-locked RAM copy (--resident-experts) that follows the traffic between requests
# (STRATA_RAM_ADAPT=256, learned placement saved to expert-profile-learned.bin); the two cards overlap decode
# windows (--pipeline-windows 2 --adapt-async 1); a conversation of 1,024+ tokens is parked when it grew by 4,096
# (--conversation-cache-mib 1024, 8 slots, --conversation-cache-park-gain 4096), one too big to park goes to disk
# when another conversation comes in and comes back in ~3 s (--conversation-spill-dir, --no-conversation-spill-idle);
# a system prompt seen before is restored from disk (--prefix-cache-dir); the refusal direction is projected out
# at runtime (--control-vector-scaled); the Sharp chat template at xhigh effort (the pack's tokenizer-sharp).
# Knobs: CONFIG= another config in strata/, PORT=, HOST= (default 127.0.0.1).  Strata 0.2.1 refuses a non-loopback
# bind without an API key: HOST=0.0.0.0 needs an API key set (see the server's --help); clients then
# send it as a Bearer token.  Measured numbers: docs/benchmarks.md.
set -euo pipefail
cd "$(dirname "$0")/../strata"
CONFIG=${CONFIG:-strata-flash-next-262k.json}
PORT=${PORT:-8888}
HOST=${HOST:-127.0.0.1}
[ -f "$CONFIG" ] || { echo "missing $CONFIG: run ./install.sh first" >&2; exit 1; }
PACK=$(python3 -c 'import json,sys; a=json.load(open(sys.argv[1]))["args"]; print(a[a.index("--pack")+1])' "$CONFIG")
[ -f "$PACK/dense.bin" ] && [ -f mtp/rt/experts.bin ] || { echo "run ./prepare.sh first (QUANT=IQ3_XXS for the IQ3_XXS config)" >&2; exit 1; }
ss -ltn | grep -q ":$PORT " && { echo "port $PORT is already listening" >&2; exit 1; }
pgrep -x strata >/dev/null && { echo "a strata engine is already running" >&2; exit 1; }
exec .venv/bin/python -m serve.server --engine strata --config "$CONFIG" --host "$HOST" --port "$PORT"
