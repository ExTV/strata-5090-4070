#!/usr/bin/env bash
# Clones upstream Strata at the v0.1.39 tag into ./strata, applies the patch series in patches/ (Hardin22's two-GPU
# PRs, twelve other open PRs and our own patches, in the order they were merged and tested), builds the engine and the vision helper
# for an RTX 5090 (sm_120) + RTX 4070 Ti SUPER (sm_89), makes the Python venv, and writes the server config
# from configs/flash-next-262k.json.in with $MODELS filled in.  Safe to re-run: patches already applied are
# skipped and cmake only rebuilds what changed.  The expert pack and the MTP drafter are built by prepare.sh.
set -euo pipefail
cd "$(dirname "$0")"

STRATA_REPO=${STRATA_REPO:-https://github.com/Niko1221/Strata.git}
STRATA_COMMIT=${STRATA_COMMIT:-6f32ec070f23ced9f50e704d854d775da52591ab}   # tag v0.1.39 (2026-10-04)
MODELS=${MODELS:-$PWD/models}
CUDA_ARCHS=${CUDA_ARCHS:-"89;120"}
JOBS=${JOBS:-3}          # a cicc/nvcc job takes ~3 GB of RAM; 3 jobs fit a 32 GB box next to a desktop

for t in git patch cmake ninja nvcc; do
    command -v $t >/dev/null || { echo "$t is required (nvcc: put the CUDA toolkit's bin on PATH)" >&2; exit 1; }
done

if [ ! -d strata ]; then
    git clone "$STRATA_REPO" strata
    git -C strata checkout --quiet "$STRATA_COMMIT"
fi
cd strata
have=$(git rev-parse HEAD)
[ "$have" = "$STRATA_COMMIT" ] || { echo "./strata is at $have, not $STRATA_COMMIT; remove it or set STRATA_COMMIT" >&2; exit 1; }

# The patches overlap (later ones edit lines earlier ones added), so a re-run cannot test each one by reversing
# it: .patches-applied records what this tree already has.
touch .patches-applied
for p in ../patches/[0-9][0-9]-*.patch; do
    name=$(basename "$p")
    if grep -qxF "$name" .patches-applied; then
        echo "already applied  $name"
    elif patch -p1 --dry-run --forward --quiet < "$p" >/dev/null 2>&1; then
        patch -p1 --forward --quiet -b -z .orig-v0139 < "$p"
        echo "$name" >> .patches-applied
        echo "applied          $name"
    else
        echo "does not apply   $name" >&2; exit 1
    fi
done

if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
    .venv/bin/python -m pip install --quiet -r requirements.txt
fi

# The engine. STRATA_ENABLE_CUDA is OFF by default (CPU tools only); the pinned llama.cpp commit is fetched by
# cmake for ggml (or point STRATA_GGML_DIR at a local checkout of that commit).
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_CUDA=ON -DSTRATA_NATIVE_EXPERTS=ON \
      -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCHS" ${STRATA_GGML_DIR:+-DSTRATA_GGML_DIR=$STRATA_GGML_DIR}
cmake --build build -j"$JOBS"

# The image encoder (llama.cpp's mtmd at the same pinned commit), on the GPU.
LLAMA_DIR=${STRATA_GGML_DIR:-$PWD/build/_deps/strata_llamacpp-src}
cmake -S tools/vision -B build-vision -G Ninja -DCMAKE_BUILD_TYPE=Release -DLLAMA_DIR="$LLAMA_DIR" \
      -DSTRATA_VISION_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCHS"
cmake --build build-vision --target strata-vision -j"$JOBS"

MODELS="$MODELS" python3 -c 'import os,sys; sys.stdout.write(open("../configs/flash-next-262k.json.in").read().replace("@MODELS@", os.environ["MODELS"]))' > strata-flash-next-262k.json
echo "$MODELS" > models.path      # prepare.sh and the launcher read it, so MODELS= is needed only here
sha256sum -c --quiet ../patches/MANIFEST.sha256 && echo "the $(wc -l < ../patches/MANIFEST.sha256) patched files match patches/MANIFEST.sha256 (the tested tree)"
echo
echo "built: strata/build/strata, strata/build-vision/bin/strata-vision; config strata/strata-flash-next-262k.json (MODELS=$MODELS)"
echo "next: download the model into $MODELS (README step 2), then ./prepare.sh, then launchers/flash-next-262k.sh"
