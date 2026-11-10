#!/usr/bin/env bash
# Qwen3.8-Flash-Next (Unsloth V3.1 UD-IQ3_XXS with Unsloth's Q8_0 PLE table, the shipped config;
# CONFIG=strata-flash-next-262k.json for ISTA GSQ-RCO IQ3_S, strata-flash-next-iq3xxs-262k.json for IQ3_XXS)
# at 262,144 tokens on an RTX 5090 + RTX 4070 Ti SUPER, served by the patched Strata on :8888 (OpenAI and Anthropic
# compatible, model name qwen3.8-flash-next, images on).
# Layers 0-38 on the 5090, 39-47, the drafter and the image encoder on the 4070; prompts read on the 5090
# (--prefill-main) in 4,096-token chunks, the parts up to the whole context split-wise so each card runs its own
# layers (--prefill-main-small); the draft layer's K/V computed there too (STRATA_PM_MTP_BATCH=1); the experts
# neither card holds sit in a page-locked RAM copy (--resident-experts --resident-budget-gib 14.7: all of them plus
# every cache slot the prompt path borrows) that follows the traffic between requests (STRATA_RAM_ADAPT=256,
# learned placement saved to expert-profile-learned-udiq3.bin); the two cards overlap decode windows
# (--pipeline-windows 2 --adapt-async 1); the engine's helper threads run on spare CPUs and the host thread on the
# first core's SMT sibling (--aux-cpus auto --host-core sibling); no conversation parking, spill or prefix store
# (the box has 32 GB of RAM; the IQ3_S config still has them); the refusal direction is projected out at runtime
# (--control-vector-scaled); the Sharp chat template at xhigh effort (the pack's tokenizer-sharp).
# Knobs: CONFIG= another config in strata/, PORT=, HOST= (default 127.0.0.1).  Strata 0.2.1 refuses a non-loopback
# bind without an API key: HOST=0.0.0.0 needs an API key set (see the server's --help); clients then
# send it as a Bearer token.  Measured numbers: docs/benchmarks.md.
set -euo pipefail
cd "$(dirname "$0")/../strata"
CONFIG=${CONFIG:-strata-flash-next-ud-iq3xxs-262k.json}
PORT=${PORT:-8888}
HOST=${HOST:-127.0.0.1}
[ -f "$CONFIG" ] || { echo "missing $CONFIG: run ./install.sh first" >&2; exit 1; }
PACK=$(python3 -c 'import json,sys; a=json.load(open(sys.argv[1]))["args"]; print(a[a.index("--pack")+1])' "$CONFIG")
[ -f "$PACK/dense.bin" ] && [ -f mtp/rt/experts.bin ] || { echo "run ./prepare.sh first (QUANT=IQ3_S or IQ3_XXS for the ISTA configs)" >&2; exit 1; }
ss -ltn | grep -q ":$PORT " && { echo "port $PORT is already listening" >&2; exit 1; }
pgrep -x strata >/dev/null && { echo "a strata engine is already running" >&2; exit 1; }
exec .venv/bin/python -m serve.server --engine strata --config "$CONFIG" --host "$HOST" --port "$PORT"
