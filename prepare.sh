#!/usr/bin/env bash
# One-time model preparation inside ./strata, for one quant (QUANT=IQ3_S, the shipped one, or IQ3_XXS): the dense
# pack (attention, norms, tokenizer; the experts stay in the GGUF and are mmap'd by the engine), the MTP draft
# runtime from the base model's draft head, and the pack's second tokenizer directory with the Sharp chat template
# at xhigh effort.  Needs the GGUF shards in $MODELS/$QUANT/ (README step 2).  Skips what already exists.
set -euo pipefail
cd "$(dirname "$0")/strata"
MODELS=${MODELS:-$(cat models.path 2>/dev/null || echo "$PWD/../models")}   # models.path is written by install.sh
QUANT=${QUANT:-IQ3_S}
PACK=packs/gsq-$(echo "$QUANT" | tr '[:upper:]' '[:lower:]')
SHARD1=$MODELS/$QUANT/Qwen3.8-Flash-Next-GSQ-RCO-$QUANT-00001-of-00002.gguf
[ -f "$SHARD1" ] || { echo "missing $SHARD1 (README step 2)" >&2; exit 1; }
export STRATA_GGUF_PY=${STRATA_GGUF_PY:-$PWD/build/_deps/strata_llamacpp-src/gguf-py}

if [ ! -f "$PACK/dense.bin" ]; then
    .venv/bin/python tools/iq_pack.py --gguf "$SHARD1" --out "$PACK"                # ~1.5 GB, a few seconds to minutes
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
    echo "$TEMPLATE_SHA  $PACK/tokenizer-sharp/chat_template.jinja" | sha256sum -c --quiet
    sed -i "s/^{%- set _default_reasoning_effort = 'medium' %}$/{%- set _default_reasoning_effort = 'xhigh' %}/" "$PACK/tokenizer-sharp/chat_template.jinja"
    echo "$XHIGH_SHA  $PACK/tokenizer-sharp/chat_template.jinja" | sha256sum -c --quiet
fi

CVEC=$MODELS/Huihui-Qwen3.8-Flash-Next-refusal-direction-r.gguf
[ -f "$CVEC" ] || echo "note: $CVEC is missing; the configs project it at runtime (README step 2)" >&2
echo "pack $PACK, drafter mtp/rt and $PACK/tokenizer-sharp are ready"
