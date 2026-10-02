# strata-5090-4070

Qwen3.8-Flash-Next (the 3-bit ISTA GSQ-RCO GGUF, 76 GB of experts) with the **full 262,144-token
context** on an RTX 5090 32 GB plus an RTX 4070 Ti SUPER 16 GB in a chipset x1 slot, 31 GB of RAM,
served by [Strata](https://github.com/Niko1221/Strata) 0.1.33 with two local patches.

What you get on this hardware (details and every measurement in [docs/benchmarks.md](docs/benchmarks.md)):

| | stock Strata 0.1.33, layer split 36 | this repo |
| --- | --- | --- |
| 80K-token fresh prompt | 886-928 tok/s (the 4070 at 100%, the 5090 idle) | **1,796 tok/s** (45 s) |
| 16K fresh prompt | 470-646 tok/s | **985 tok/s** |
| 2K fresh prompt | 200-240 tok/s | **350-375 tok/s** |
| follow-up on an 80K conversation | 7.8 s | **6.1 s** |
| decode, 600-token answers, thinking off | 99-111 tok/s median | 95-108 at temperature 0, **128-134 sampled** at spec-min-p 0.7-0.8 |
| switching between two conversations (30K and 15K) | re-reads the other one: 20-48 s | **0.6-1.2 s** |
| major page faults per benchmark run | 16-24 M (the box swaps) | **14 K** |

Stock Strata refuses conversation parking with a layer split, reads every prompt through both
cards (the x1 card becomes the prompt bottleneck), and on a box with less RAM than the expert file
pays a page fault per 4 KB of expert weight whenever the kernel drops its readahead hint. The three
patches change that:

- `patches/02-prefill-main-and-parking-with-layer-split.patch`: `--prefill-main` reads the whole
  prompt on the big card (port of Strata PR #269 onto 0.1.33, rewritten for its carved sessions) and
  copies the small card's share of the state afterwards, only the cells in use; conversation parking
  works with the split (the big card's session is parked, the small card's state is copied back on
  restore). Also carries PR #487 (PCIe probe noise).
- `patches/01-upstream-0.1.35-server-stager-and-mmq-guard.patch`: from Strata 0.1.34/0.1.35:
  client-disconnect cancel (#430), per-request draft stats (#457, #460), the stager DMA wait fix
  (#385) and the MMQ tile guard (#420).
- `patches/03-pread-expert-blobs.patch`: with `STRATA_BLOB_PREAD=1` the expert pool reads each
  expert's slices with `pread` instead of `memcpy` through the mmap, so a cold expert costs one
  request instead of up to 500 synchronous page faults. Together with `--prefill auto:32768` this is
  what took the 80K prompt from 510-700 tok/s to 1,796.

All three patches apply to a pristine v0.1.33 checkout and reproduce the tested tree byte for byte.
PR #439 (batched expert gathers) is deliberately **not** included: under `--prefill-main` it
deadlocks on the second prompt chunk of a fully streamed layer ([docs/how-it-works.md](docs/how-it-works.md)).

## What you need

- An RTX 5090 (or another 32 GB Blackwell card) plus a second NVIDIA card with 16 GB; the second
  card can sit on a chipset x1 slot. The layer split (36) and the expert-cache sizes below are for
  exactly 32 + 16 GB.
- Linux, NVIDIA driver, CUDA toolkit (nvcc), cmake, ninja, git, patch, Python 3.10+.
- 32 GB of RAM and a fast NVMe with ~80 GB free for the model. The experts are mmap'd from the
  GGUF; RAM holds the page cache, the pinned KV (3 GB) and parked conversations (up to 6 GB).

## Step 1: build

```bash
git clone https://github.com/ExTV/strata-5090-4070.git && cd strata-5090-4070
./install.sh            # clones Strata v0.1.33 into ./strata, patches, builds engine + vision helper, venv
```

`JOBS=3` by default (each CUDA compile job takes ~3 GB of RAM). `MODELS=` sets where the GGUF
lives (default `./models`); it is written into `strata/strata-flash-next-262k.json`.

## Step 2: download the model

```bash
pip install -U huggingface_hub
hf download ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF --include "IQ3_XXS/*" "mmproj-*" --local-dir models
mv models/IQ3_XXS/* models/ && rmdir models/IQ3_XXS
./prepare.sh            # builds the dense pack (packs/gsq-iq3_xxs) and the MTP draft runtime (mtp/rt)
```

Shard 1 (47 GB) holds the experts and is read in place; shard 2 (28.8 GB) is the PLE table.
`prepare.sh` runs Strata's own `tools/iq_pack.py`, `mtp_fetch.py`, `mtp_pack.py`, `mtp_rt.py`.

## Step 3: run

```bash
launchers/flash-next-262k.sh
```

Serves `http://0.0.0.0:8888/v1` (OpenAI chat completions, Anthropic messages, model name
`qwen3.8-flash-next`, images on). The config is `strata/strata-flash-next-262k.json`; `CONFIG=`,
`PORT=`, `HOST=` override. Sampling defaults are 0.6 / 0.95 / 20; a request can override them, and
can tune the drafter per request with `"strata_tune": {"spec_min_p": 0.8}` in the body.

## RAM: the one thing to know

A 76 GB expert file streamed through 24 GB of page cache means every long prompt reads most of the
model from NVMe, and the kernel also pushes the engine's own heap out to swap to make room for
file pages it cannot reuse. Prompt speed then depends on how many of the expert reads turn into
synchronous page faults: 80K prompts measured 1,250 tok/s with 1-6 M major faults and 640-700
tok/s with 10-20 M, on identical configs, between boots. `tools/snapshot.py` prints the counters
(`pgmajfault`, `pswpin`, NVMe bytes); diff them around a prompt before believing any A/B. Lowering
`vm.swappiness` to 10 did not change it. Two things did, both in the shipped config: bigger prompt
chunks (`--prefill auto:32768`: every chunk re-streams the experts of every layer, so four times
fewer chunks took the 80K prompt from 510 tok/s and 24 M faults to 1,451 and 1.1 M), and patch 03
(`pread` instead of page faults: 1,451 -> 1,796 tok/s, 951 K -> 14 K faults, 3.2 GB -> 47 MB of
swap-ins, back to back). Details in [docs/how-it-works.md](docs/how-it-works.md) and the numbers in
[docs/benchmarks.md](docs/benchmarks.md). Strata's own sizing rule is RAM >= shard 1 plus 10 GB
(57 GB for this quant); this setup runs well below that, which is why the counters matter.

## Tools

`tools/bench.py NAME` (5 decodes + 2K/16K/80K fresh prompts + follow-up, one JSON line),
`tools/decode_after.py NAME` (decode right after a big prompt), `tools/needle_followups.py` (40K
needle, four follow-ups, a 20K extension), `tools/parking_check.py` (two alternating conversations,
correctness and switch time), `tools/spec_min_p_sweep.py NAME` (per-request drafter threshold A/B, no
restart), `tools/snapshot.py` (fault/swap/NVMe/GPU counters). All talk to `127.0.0.1:8888`.

License: MIT. Strata itself is MIT (LICENSE.strata).
