#!/usr/bin/env bash
# Clones upstream Strata at the v0.2.1 tag into ./strata, applies the patch series in patches/ (our dual-GPU
# series merged onto v0.2.1, one upstream PR, one upstream commit and our own fixes, in the order they were merged
# and tested), builds the engine and the vision helper for an RTX 5090 (sm_120) + RTX 4070 Ti SUPER (sm_89), makes
# the Python venv, and writes the three server configs from configs/*.json.in with $MODELS filled in.  Safe to
# re-run: patches already applied are skipped and cmake only rebuilds what changed.  The expert pack, the MTP
# drafter and the chat template are prepared by prepare.sh.
set -euo pipefail
cd "$(dirname "$0")"

STRATA_REPO=${STRATA_REPO:-https://github.com/Niko1221/Strata.git}
STRATA_COMMIT=${STRATA_COMMIT:-90767252f420e25223c739d604145ad15911d48b}   # tag v0.2.1
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
        patch -p1 --forward --quiet -b -z .orig-v021 < "$p"
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
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_CUDA=ON -DSTRATA_NATIVE_EXPERTS=ON -DSTRATA_BUILD_TESTS=OFF \
      -DSTRATA_MMQ_KQUANTS=OFF -DSTRATA_Q6K_EXPERTS=OFF -DSTRATA_MMQ_TQ_OVERLAY=OFF \
      -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCHS" ${STRATA_GGML_DIR:+-DSTRATA_GGML_DIR=$STRATA_GGML_DIR}
cmake --build build --target strata -j"$JOBS"

# The image encoder (llama.cpp's mtmd at the same pinned commit), on the GPU.
LLAMA_DIR=${STRATA_GGML_DIR:-$PWD/build/_deps/strata_llamacpp-src}
cmake -S tools/vision -B build-vision -G Ninja -DCMAKE_BUILD_TYPE=Release -DLLAMA_DIR="$LLAMA_DIR" \
      -DSTRATA_VISION_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCHS"
cmake --build build-vision --target strata-vision -j"$JOBS"

for c in flash-next-ud-iq3xxs-262k flash-next-262k flash-next-iq3xxs-262k; do
    MODELS="$MODELS" python3 -c 'import os,sys; sys.stdout.write(open(sys.argv[1]).read().replace("@MODELS@", os.environ["MODELS"]))' \
        "../configs/$c.json.in" > "strata-$c.json"
done
echo "$MODELS" > models.path      # prepare.sh and the launcher read it, so MODELS= is needed only here
sha256sum -c --quiet ../patches/MANIFEST.sha256 && echo "the $(wc -l < ../patches/MANIFEST.sha256) patched files match patches/MANIFEST.sha256 (the tested tree)"
echo
echo "built: strata/build/strata, strata/build-vision/bin/strata-vision; configs strata/strata-flash-next-ud-iq3xxs-262k.json"
echo "       (Unsloth UD-IQ3_XXS, the shipped one), strata-flash-next-262k.json (IQ3_S) and strata-flash-next-iq3xxs-262k.json, MODELS=$MODELS"
echo "next: download the model into $MODELS (README step 2), then ./prepare.sh, then launchers/flash-next-262k.sh"
