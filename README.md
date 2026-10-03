# strata-5090-4070

Qwen3.8-Flash-Next (the 3-bit ISTA GSQ-RCO GGUF, 76 GB of experts) with the **full 262,144-token
context** on an RTX 5090 32 GB plus an RTX 4070 Ti SUPER 16 GB in a chipset x1 slot, 31 GB of RAM,
served by [Strata](https://github.com/Niko1221/Strata) through
[Hardin22's Strata-DualGPU fork](https://github.com/Hardin22/Strata-DualGPU) (Strata 0.1.38 plus a RAM
copy of the experts on a layer split and pipelined decode windows), six open upstream PRs, and two
patches of our own.

What you get on this hardware (details and every measurement in [docs/benchmarks.md](docs/benchmarks.md)):

| | stock Strata 0.1.33, layer split 36 | this repo |
| --- | --- | --- |
| decode, 600-token answers, thinking off, greedy | 99-111 tok/s median | **170 tok/s** (136-190) |
| decode right after an 80K prompt | | **155 tok/s** |
| 80K-token fresh prompt | 886-928 tok/s (the 4070 at 100%, the 5090 idle) | **2,120 tok/s** (38 s) |
| 16K fresh prompt | 470-646 tok/s | **1,360 tok/s** |
| 2K fresh prompt | 200-240 tok/s | **450-460 tok/s** |
| follow-up on an 80K conversation | 7.8 s | **4.4 s** |
| switching between two conversations (30K and 15K) | re-reads the other one: 20-48 s | **0.4-0.5 s** |
| major page faults per benchmark run | 16-24 M (the box swaps) | **under 20 K** |

Stock Strata refuses the RAM copy of the experts and conversation parking on a layer split, reads every
prompt through both cards (the x1 card becomes the prompt bottleneck), and on a box with less RAM than
the expert file pays a page fault per 4 KB of expert weight whenever the kernel drops its readahead
hint. The fork and the patches change that:

- **The fork** (pinned by commit in `install.sh`): `--resident-experts` works with `--layer-split`, so
  the experts neither card holds (about 7 GB here) sit page-locked in RAM and nothing is read from the
  SSD while the model answers; `--pipeline-windows` runs the next speculative window on the 5090 while
  the 4070 still verifies the current one; the adaptive expert tier no longer stalls a window; the two
  stages hand off through device flags instead of host waits; a separate VRAM reserve for the second
  card. Its author's write-up: `docs/DUAL_GPU.md` in that repo. This was its first build on Linux.
- `patches/01` to `06`: open Strata PRs, applied as they were on 2026-10-03. #603 adds a top-k kernel
  for selections past the 135K-cell register fit (at a 262K context the 5090 otherwise ran the old
  six-pass kernel on every prompt batch and decode window); #547 lends 1.25 GiB fewer expert slots to a
  32K prompt chunk; #567 tokenises only the new turn of a conversation; #510, #572 and #525 fix
  three tool-call shapes agent clients produce (malformed arguments in history, an unfinished call,
  a call stranded inside an unclosed thinking span).
- `patches/07-prefill-main-and-parking-with-layer-split.patch`: `--prefill-main` reads the whole
  prompt on the big card (port of Strata PR #269, closed unmerged) and copies the small card's share
  of the state afterwards, only the cells in use; conversation parking works with the split (the big
  card's session is parked, the small card's state is copied back on restore). Cost: the pinned host
  K/V of the small card's 12 layers exists twice, about 0.77 GiB.
- `patches/08-pread-expert-blobs.patch`: with `STRATA_BLOB_PREAD=1` the expert pool reads each
  expert's slices with `pread` instead of `memcpy` through the mmap, so a cold expert costs one
  request instead of up to 500 synchronous page faults.

Also in the shipped config: `STRATA_PF_FUSED=1`, Strata 0.1.36's fused int8 tensor-core prompt kernels
for the native IQ packs (every expert tensor type in this GGUF is covered; +9-13% on prompts here).

All eight patches apply in order to a pristine checkout of the pinned fork commit;
`patches/MANIFEST.sha256` holds the sha256 of the 18 patched files as tested, `install.sh` checks it,
and the CI job does the same. Earlier releases of this repo targeted v0.1.33 and v0.1.37 (PR #385 and the
0.1.35 server hunks are upstream now). PR #439 (batched expert gathers) is deliberately **not**
included: under `--prefill-main` it deadlocks on the second prompt chunk of a fully streamed layer
([docs/how-it-works.md](docs/how-it-works.md)).

## What you need

- An RTX 5090 (or another 32 GB Blackwell card) plus a second NVIDIA card with 16 GB; the second
  card can sit on a chipset x1 slot. The layer split (36) and the VRAM reserves are for exactly
  32 + 16 GB.
- Linux, NVIDIA driver, CUDA toolkit (nvcc), cmake, ninja, git, patch, Python 3.10+.
- 32 GB of RAM and a fast NVMe with ~80 GB free for the model. RAM holds the 7 GB expert copy, the
  pinned KV (3 GB), parked conversations (4 GB) and the page cache for the rest; with the model up
  about 8 GB stays free. 64 GB would let the parking budget and the page cache grow (see below).

## Step 1: build

```bash
git clone https://github.com/ExTV/strata-5090-4070.git && cd strata-5090-4070
./install.sh            # clones the fork at the pinned commit into ./strata, patches, builds engine + vision helper, venv
```

`JOBS=3` by default (each CUDA compile job takes ~3 GB of RAM). `MODELS=` sets where the GGUF
lives (default `./models`); it is written into `strata/strata-flash-next-262k.json`.

## Step 2: download the model

```bash
strata/.venv/bin/pip install -U huggingface_hub
strata/.venv/bin/hf download ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF --include "IQ3_XXS/*" "mmproj-*" --local-dir models
mv models/IQ3_XXS/* models/ && rmdir models/IQ3_XXS
./prepare.sh            # builds the dense pack (packs/gsq-iq3_xxs) and the MTP draft runtime (mtp/rt)
```

Shard 1 (47 GB) holds the experts and is read in place; shard 2 (28.8 GB) is the PLE table.
`prepare.sh` runs Strata's own `tools/iq_pack.py`, `mtp_fetch.py`, `mtp_pack.py`, `mtp_rt.py`.

## Step 3: run

```bash
launchers/flash-next-262k.sh
```

Serves `http://127.0.0.1:8888/v1` (OpenAI chat completions, Anthropic messages, model name
`qwen3.8-flash-next`, images on). The config is `strata/strata-flash-next-262k.json`; `CONFIG=`,
`PORT=`, `HOST=` override. There is no authentication: `HOST=0.0.0.0` exposes the endpoint, image
input included, to everything on your network, so only do that behind a firewall rule or a proxy
that adds auth. Sampling defaults are 0.6 / 0.95 / 20; a request can override them, and
can tune the drafter per request with `"strata_tune": {"spec_min_p": 0.8}` in the body.

## RAM: the one thing to know

The expert file is 47 GB and the box has 31 GB. Three things compete for that RAM: the 7 GB copy of
the experts the cards do not hold (decode never touches the SSD because of it), parked conversations
(a 130K-token conversation is 2.7-2.9 GB; the budget is 4 GB, so one long session parks, two
alternate by re-reading each other, 57 s each time), and the page cache the prompt path streams
experts through. The prompt path borrows about 10 GiB of the 5090's expert cache for its buffers on
every prompt and re-streams the lent experts from the file, so an 80K prompt still reads about 100 GB
from NVMe; that is the remaining floor on prompts and on the 2-4 s a short follow-up costs, and it is
why the fork's author and we both land on "more RAM". The measured no-build alternatives (a different
split, the stock split prefill, more PLE reads in flight, parking off) are in
[docs/benchmarks.md](docs/benchmarks.md); none moved it.

`tools/snapshot.py` prints the counters (`pgmajfault`, `pswpin`, NVMe bytes); diff them around a
prompt before believing any A/B.

## Tools

`tools/bench.py NAME` (5 decodes + 2K/16K/80K fresh prompts + follow-up, one JSON line),
`tools/decode_after.py NAME` (decode right after a big prompt), `tools/needle_followups.py` (40K
needle, four follow-ups, a 20K extension), `tools/parking_check.py` (two alternating conversations,
correctness and switch time), `tools/spec_min_p_sweep.py NAME` (per-request drafter threshold A/B, no
restart), `tools/snapshot.py` (fault/swap/direct-reclaim/NVMe/GPU counters). All talk to `127.0.0.1:8888`
unless `STRATA_URL` says otherwise. The bench prompts are random words seeded from the run name
(crc32), so two runs of the same name read identical prompts.

License: MIT. Strata and the fork are MIT (LICENSE.strata).
