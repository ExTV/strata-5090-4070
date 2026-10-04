# strata-5090-4070

Qwen3.8-Flash-Next (the 3-bit ISTA GSQ-RCO GGUF, 76 GB of experts) with the **full 262,144-token
context** on an RTX 5090 32 GB plus an RTX 4070 Ti SUPER 16 GB in a chipset x1 slot, 31 GB of RAM,
served by [Strata](https://github.com/Niko1221/Strata) through
[Hardin22's Strata-DualGPU fork](https://github.com/Hardin22/Strata-DualGPU) (Strata 0.1.38 plus a RAM
copy of the experts on a layer split and pipelined decode windows), six open upstream PRs, and four
patches of our own.

What you get on this hardware (details and every measurement in [docs/benchmarks.md](docs/benchmarks.md)):

| | stock Strata 0.1.33, layer split 36 | this repo |
| --- | --- | --- |
| decode, 600-token answers, thinking off, greedy | 99-111 tok/s median | **170-179 tok/s** (131-197) |
| decode right after an 80K prompt | | **160-180 tok/s** |
| 80K-token fresh prompt | 886-928 tok/s (the 4070 at 100%, the 5090 idle) | **2,130 tok/s** (38 s) |
| 16K fresh prompt | 470-646 tok/s | **2,165 tok/s** |
| 2K fresh prompt | 200-240 tok/s | **560-580 tok/s** |
| follow-up on an 80K conversation | 7.8 s | **3.7 s** |
| a 3K-token tool result on a running chat | | **3.6 s** |
| a 150-token message on a running chat | | **0.5 s** |
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
  card; each card keeps the dense weights of its own layers only (here the 4070 frees 2.4 GiB and
  holds every expert of its 12 layers). Its author's write-up: `docs/DUAL_GPU.md` in that repo.
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
  K/V of the small card's 12 layers exists twice, about 0.77 GiB, and the big card keeps the dense
  weights of all 48 layers (the fork would otherwise drop the ones the prompt path reads there).
- `patches/08-pread-expert-blobs.patch`: with `STRATA_BLOB_PREAD=1` the expert pool reads each
  expert's slices with `pread` instead of `memcpy` through the mmap, so a cold expert costs one
  request instead of up to 500 synchronous page faults.
- `patches/09-lend-region-in-ram-with-layer-split.patch`: with `STRATA_RESIDENT_LEND=1` the experts of
  the cache slots the prompt path borrows are kept in page-locked RAM on a layer split too (stock and
  the fork do this on one GPU only), as far as RAM allows. Prompts then read them at PCIe speed
  instead of re-reading them from the SSD: 16K prompts 1,280 -> 2,170 tok/s, a 3K-token tool result
  5.0 -> 3.6 s, decode unchanged.
- `patches/10-merged-tool-turns-and-tag-in-prose.patch` (server, Python): some chat apps keep one
  assistant message per user turn and send every tool call of the turn in it, followed by all the
  results. The model wrote them step by step, so each new call moves in front of the earlier results
  and the engine re-reads the whole turn on every step (measured: 19 requests in a row re-reading 24K
  to 134K tokens). Tool call ids now name the response that issued them and such a message is split
  back into its steps, so each step reads only the new result. Also: a `<tool_call>` tag named in a
  sentence is text, not the start of a call.

Also in the shipped config: `STRATA_PF_FUSED=1`, Strata 0.1.36's fused int8 tensor-core prompt kernels
for the native IQ packs (every expert tensor type in this GGUF is covered; +9-13% on prompts here).

All ten patches apply in order to a pristine checkout of the pinned fork commit;
`patches/MANIFEST.sha256` holds the sha256 of the 19 patched files as tested, `install.sh` checks it,
and the CI job does the same. Earlier releases of this repo targeted v0.1.33 and v0.1.37 (PR #385 and the
0.1.35 server hunks are upstream now). PR #439 (batched expert gathers) is deliberately **not**
included: under `--prefill-main` it deadlocks on the second prompt chunk of a fully streamed layer
([docs/how-it-works.md](docs/how-it-works.md)).

## What you need

- An RTX 5090 (or another 32 GB Blackwell card) plus a second NVIDIA card with 16 GB; the second
  card can sit on a chipset x1 slot. The layer split (36) and the VRAM reserves are for exactly
  32 + 16 GB.
- Linux, NVIDIA driver, CUDA toolkit (nvcc), cmake, ninja, git, patch, Python 3.10+.
- 32 GB of RAM and a fast NVMe with ~80 GB free for the model. RAM holds 10 GB of page-locked
  experts (the 4.8 GB no card holds plus about half of what the prompt path borrows), the pinned KV
  (3 GB) and parked conversations (up to 4 GB); with the model up 2.3 to 6 GB stays available. This
  config is for a headless box: there is no VRAM for a desktop either. With 64 GB every borrowed
  expert fits in RAM and long prompts gain another 50% (see below).

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
can tune the drafter per request with `"strata_tune": {"spec_min_p": 0.8}` in the body. A request
whose `max_tokens` no longer fits the context gets a shorter completion instead of a 400
(`"fit_max_tokens": true` in the config), which agent clients with a large fixed output cap need.

## RAM: the one thing to know

The expert file is 47 GB and the box has 31 GB. The 5090 holds 15,300 expert pairs, the 4070 all
6,144 of its layers, and the 3,132 neither holds sit page-locked in RAM (4.8 GiB), so decode never
touches the SSD. The prompt path borrows 6,239 of the 5090's slots (9.8 GiB) for its buffers on every
32K chunk and has to stream the experts that lived there while it reads; from the SSD that is about
100 GB per 80K prompt and the floor on every prompt. Patch 09 keeps those experts in locked RAM too,
from the last slot down, with what RAM is left:

| locked experts | 80K prompt | 16K | 3K tool result | lowest available RAM | parking |
| --- | --- | --- | --- | --- | --- |
| 4.8 GiB (the fork) | 2,127 tok/s | 1,282 | 5.0 s | 5 GB | works |
| **10 GiB (shipped, `STRATA_RESIDENT_HEADROOM_GIB=10`)** | 2,130 | **2,165** | **3.6 s** | 2.3 GB | works, about 3 GB of chats |
| 14.6 GiB (all of it, headroom 4) | **3,173** | 2,177 | 3.8 s | 1.1 GB | refused |

With everything locked the box has about 1 GB available and the engine refuses to park conversations
(it keeps a 2.5 GB floor), so every switch between chats, and every side request a client sends
between turns, re-reads the conversation. The shipped 10 GiB covers the loan of a chunk up to about
17K tokens: everything but the long first read of a big paste gets the gain, and parking keeps
working (a 130K-token conversation is 2.7-2.9 GB). With 64 GB of RAM drop the headroom line and take
the last row. Decode is the same in all three. The measured no-build alternatives (a different split,
the stock split prefill, more PLE reads in flight, parking off) are in
[docs/benchmarks.md](docs/benchmarks.md); none moved prompts.

Two more settings in the config follow from the same numbers. `--short-read 768`: the batched prompt
path costs about 1.6 s before its first token here, a decode window about 2.2 ms a token, so new text
up to 768 tokens goes through the windows (a 150-token message: 1.7 -> 0.5 s; the default of 64 is
for machines with slower windows). `--conversation-cache-slots 8`: chat apps send small side requests
(titles, summaries) that each take a slot; with 4 they pushed the long conversation out.

`tools/snapshot.py` prints the counters (`pgmajfault`, `pswpin`, NVMe bytes); diff them around a
prompt before believing any A/B.

## Tools

`tools/bench.py NAME` (5 decodes + 2K/16K/80K fresh prompts + follow-up, one JSON line),
`tools/decode_after.py NAME` (decode right after a big prompt), `tools/needle_followups.py` (40K
needle, four follow-ups, a 20K extension), `tools/parking_check.py` (two alternating conversations,
correctness and switch time), `tools/merged_tool_turn.py` (a client that merges a turn's tool calls
into one message; `OLD_IDS=1` shows the re-reads patch 10 removes), `tools/step_times.py NAME TEXTFILE`
(tool-result sized reads on real text), `tools/spec_min_p_sweep.py NAME` (per-request drafter threshold A/B, no
restart), `tools/snapshot.py` (fault/swap/direct-reclaim/NVMe/GPU counters). All talk to `127.0.0.1:8888`
unless `STRATA_URL` says otherwise. The bench prompts are random words seeded from the run name
(crc32), so two runs of the same name read identical prompts.

License: MIT. Strata and the fork are MIT (LICENSE.strata).
