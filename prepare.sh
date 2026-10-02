#!/usr/bin/env bash
# One-time model preparation inside ./strata: the dense pack (attention, norms, tokenizer; the experts stay in the
# GGUF and are mmap'd by the engine) and the MTP draft runtime from the base model's draft head.  Needs the GGUF
# shards in $MODELS (README step 2).  Skips what already exists.
set -euo pipefail
cd "$(dirname "$0")/strata"
MODELS=${MODELS:-$(cat models.path 2>/dev/null || echo "$PWD/../models")}   # models.path is written by install.sh
SHARD1=$MODELS/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf
[ -f "$SHARD1" ] || { echo "missing $SHARD1 (README step 2)" >&2; exit 1; }
export STRATA_GGUF_PY=${STRATA_GGUF_PY:-$PWD/build/_deps/strata_llamacpp-src/gguf-py}

if [ ! -f packs/gsq-iq3_xxs/dense.bin ]; then
    .venv/bin/python tools/iq_pack.py --gguf "$SHARD1" --out packs/gsq-iq3_xxs      # ~1.5 GB, a few minutes
fi
if [ ! -f mtp/rt/experts.bin ]; then
    .venv/bin/python tools/mtp_fetch.py fetch --out mtp                              # the base model's MTP head
    .venv/bin/python tools/mtp_pack.py --src mtp --experts q2_0 --out mtp/mtp-q2_0.gguf
    .venv/bin/python tools/mtp_rt.py --gguf mtp/mtp-q2_0.gguf --out mtp/rt
    cp data/draft_vocab.bin mtp/rt/draft_vocab.bin
fi
echo "pack packs/gsq-iq3_xxs and drafter mtp/rt are ready"
