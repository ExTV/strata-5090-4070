#!/usr/bin/env bash
# One-time model preparation inside ./strata, for one quant: QUANT=UD-IQ3_XXS (Unsloth's, the shipped config),
# IQ3_S or IQ3_XXS (ISTA GSQ-RCO).  Builds the dense pack (attention, norms, tokenizer; the experts stay in the
# GGUF and are mmap'd by the engine), the MTP draft runtime from the base model's draft head, the pack's second
# tokenizer directory with the Sharp chat template at xhigh effort, and the PLE table the config reads: Unsloth's
# Q8_0 table for UD-IQ3_XXS, the FP8 table for the ISTA quants.  Needs the GGUF shards in $MODELS/$QUANT/
# (README step 2).  Skips what already exists.
set -euo pipefail
cd "$(dirname "$0")/strata"
MODELS=${MODELS:-$(cat models.path 2>/dev/null || echo "$PWD/../models")}   # models.path is written by install.sh
QUANT=${QUANT:-UD-IQ3_XXS}
PACK_ARGS=()
case "$QUANT" in
    UD-IQ3_XXS)
        PACK=packs/unsloth-ud-iq3_xxs-v31
        SHARD1=$MODELS/$QUANT/Qwen3.8-Flash-Next-UD-IQ3_XXS-00001-of-00004.gguf
        PACK_ARGS=(--compat-bf16)        # 195 Q8_0 hyper-connection tensors rounded to the BF16 the engine reads
        PLE_KIND=q8 ;;
    *)
        PACK=packs/gsq-$(echo "$QUANT" | tr '[:upper:]' '[:lower:]')
        SHARD1=$MODELS/$QUANT/Qwen3.8-Flash-Next-GSQ-RCO-$QUANT-00001-of-00002.gguf
        PLE_KIND=fp8 ;;
esac
[ -f "$SHARD1" ] || { echo "missing $SHARD1 (README step 2)" >&2; exit 1; }
export STRATA_GGUF_PY=${STRATA_GGUF_PY:-$PWD/build/_deps/strata_llamacpp-src/gguf-py}

if [ ! -f "$PACK/dense.bin" ]; then
    .venv/bin/python tools/iq_pack.py --gguf "$SHARD1" --out "$PACK" "${PACK_ARGS[@]}"                # ~1.5 GB, a few seconds to minutes
fi
if [ ! -f mtp/rt/experts.bin ]; then
    .venv/bin/python tools/mtp_fetch.py fetch --out mtp                              # the base model's MTP head
    .venv/bin/python tools/mtp_pack.py --src mtp --experts q2_0 --out mtp/mtp-q2_0.gguf
    .venv/bin/python tools/mtp_rt.py --gguf mtp/mtp-q2_0.gguf --out mtp/rt
    cp data/draft_vocab.bin mtp/rt/draft_vocab.bin
fi

# The Sharp chat template (peculiar-ragdoll/Qwen-Sharp-Chat-Templates v22.5.0, Apache-2.0), with its default
# reasoning effort raised from medium to xhigh: the pack's tokenizer directory copied, the template swapped in.
# Strata renders <tokenizer dir>/chat_template.jinja; the config's "tokenizer" key picks this directory.
TEMPLATE_URL=https://huggingface.co/peculiar-ragdoll/Qwen-Sharp-Chat-Templates/resolve/6a78b888557f8c9987f51bca98d02d8f69682044/chat_template.jinja
TEMPLATE_SHA=cdff39fb26b60dc90faa292e726655c6b21f62db497846e02e4c4bbab942a84a      # the file at that revision
XHIGH_SHA=e041a59e96f522e2497453e825ea443c02894ad0c1ef91eda14aed42f1e53395         # with the one line changed
if [ ! -f "$PACK/tokenizer-sharp/chat_template.jinja" ]; then
    command -v curl >/dev/null || { echo "curl is required to fetch the chat template" >&2; exit 1; }
    rm -rf "$PACK/tokenizer-sharp"; cp -r "$PACK/tokenizer" "$PACK/tokenizer-sharp"
    curl -sSfL "$TEMPLATE_URL" -o "$PACK/tokenizer-sharp/chat_template.jinja"
    echo "$TEMPLATE_SHA  $PACK/tokenizer-sharp/chat_template.jinja" | sha256sum -c --quiet \
        || { rm -rf "$PACK/tokenizer-sharp"; echo "chat template checksum mismatch, nothing kept" >&2; exit 1; }
    sed -i "s/^{%- set _default_reasoning_effort = 'medium' %}$/{%- set _default_reasoning_effort = 'xhigh' %}/" "$PACK/tokenizer-sharp/chat_template.jinja"
    echo "$XHIGH_SHA  $PACK/tokenizer-sharp/chat_template.jinja" | sha256sum -c --quiet \
        || { rm -rf "$PACK/tokenizer-sharp"; echo "edited chat template checksum mismatch, nothing kept" >&2; exit 1; }
fi

# The PLE n-gram table as Qwen ships it (FP8 E4M3, 51.2 GB) instead of ISTA's IQ4_NL shard 2 (8% off per row):
# the checkpoint shards that hold it are fetched at a pinned revision, copied byte for byte into one GGUF by
# Strata's tools/ple_fp8_pack.py, then deleted.  PLE_FP8=0 skips it; then point --ple-gguf back at shard 2.
FP8_REPO=Qwen/Qwen3.8-Flash-Next-FP8
FP8_REV=236dfdf285828023ca3bcd3f37366c58a3469b13
PLE=$MODELS/ple-fp8.gguf
if [ "$PLE_KIND" = fp8 ] && [ "${PLE_FP8:-1}" != 0 ] && [ ! -f "$PLE" ]; then
    SRC=$MODELS/ple-fp8-src
    .venv/bin/hf download "$FP8_REPO" model.safetensors.index.json --revision "$FP8_REV" --local-dir "$SRC"
    mapfile -t FILES < <(.venv/bin/python -c 'import json, sys
w = json.load(open(sys.argv[1]))["weight_map"]
print("\n".join(sorted({f for k, f in w.items() if ".ngram_embedding." in k})))' "$SRC/model.safetensors.index.json")
    .venv/bin/hf download "$FP8_REPO" "${FILES[@]}" --revision "$FP8_REV" --local-dir "$SRC"   # 33 files, 52 GB
    .venv/bin/python tools/ple_fp8_pack.py --model "$SRC" --out "$PLE.part" && mv "$PLE.part" "$PLE"
    rm -rf "$SRC"
fi

# UD-IQ3_XXS: Unsloth's own Q8_0 PLE table (54.4 GB; relative RMSE against the BF16 table 0.0053, FP8 0.0265,
# the IQ4_NL table in shard 4 0.0757).  One standalone GGUF; its header is patched in place so v0.2.1 loads it
# through --ple-gguf (tools/ple_header_patch.py says why; the original header is kept next to it).
PLEQ8=$MODELS/ple-q8_0.gguf
if [ "$PLE_KIND" = q8 ] && [ ! -f "$PLEQ8" ]; then
    .venv/bin/hf download unsloth/Qwen3.8-Flash-Next-GGUF engram/Qwen3.8-Flash-Next-engram-Q8_0.gguf_file --local-dir "$MODELS/engram-src"
    mv "$MODELS/engram-src/engram/Qwen3.8-Flash-Next-engram-Q8_0.gguf_file" "$PLEQ8" && rm -rf "$MODELS/engram-src"
fi
[ "$PLE_KIND" = q8 ] && python3 ../tools/ple_header_patch.py "$PLEQ8"

CVEC=$MODELS/Huihui-Qwen3.8-Flash-Next-refusal-direction-r.gguf
[ -f "$CVEC" ] || echo "note: $CVEC is missing; the configs project it at runtime (README step 2)" >&2
echo "pack $PACK, drafter mtp/rt, $PACK/tokenizer-sharp and the PLE table are ready"
