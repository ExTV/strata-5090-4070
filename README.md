# strata-5090-4070

> Qwen3.8-Flash-Next with the **full 262,144-token context** on an RTX 5090 + RTX 4070 Ti SUPER and 31 GB of RAM.

<p>
  <a href="https://github.com/ExTV/strata-5090-4070/actions/workflows/patches-apply.yml"><img src="https://github.com/ExTV/strata-5090-4070/actions/workflows/patches-apply.yml/badge.svg" alt="patches apply"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
</p>

A patched build of [Strata](https://github.com/Niko1221/Strata) for one specific box:
a 32 GB card, a 16 GB card in a chipset x1 slot, and less RAM than the 47 GB expert file.

- **Upstream Strata v0.1.40.1** plus 20 patches: ten open upstream PRs and our own work
- **190-205 tok/s decode**, prompts up to **4,040 tok/s**, a 260K-token prompt read in **83 s**
- Decode never touches the SSD: the experts no card holds sit page-locked in RAM
- Switching between conversations restores the parked one in **0.2-1.6 s**; a 200K conversation too big
  to park goes to the SSD and comes back in **3 s** instead of a 47 s re-read
- The image encoder runs on the 4070, so the 5090 keeps more experts
- A new chat with a system prompt seen before restores it from disk instead of reading it (**0.6 s** vs 11.7 s for 20K tokens)
- Agent-friendly: a 2.7K-token tool result is answered in **3.6 s**; three tool-call shapes fixed, merged tool turns split
- OpenAI and Anthropic compatible API on `:8888`, images on

## Quick start

```bash
git clone https://github.com/ExTV/strata-5090-4070.git && cd strata-5090-4070
./install.sh                    # clone Strata v0.1.40.1, apply patches, build engine + vision helper, venv
# download the model (step 2 below), then:
./prepare.sh                    # dense pack + MTP drafter
launchers/flash-next-262k.sh    # serves http://127.0.0.1:8888/v1
```

[Benchmarks](docs/benchmarks.md) · [How it works](docs/how-it-works.md) · [Issues](https://github.com/ExTV/strata-5090-4070/issues)

## Performance

### Against stock Strata on the same box

| | stock Strata 0.1.33, split 36 | this repo |
| --- | --- | --- |
| decode, 600-token answers, greedy | 99-111 tok/s | **188-205 tok/s** |
| 2K fresh prompt | 200-240 tok/s | **597-655 tok/s** |
| 16K fresh prompt | 470-646 tok/s | **2,117-2,284 tok/s** |
| 27K fresh prompt of real text | | **2,650-2,840 tok/s** (~10 s) |
| 80K fresh prompt | 886-928 tok/s | **3,146-3,281 tok/s** |
| 2K follow-up on the 80K chat | 7.9 s | **3.9-4.6 s** |
| tool results of 1.2K / 2.5K / 5.3K tokens | | **3.1-3.5 / 3.2-3.3 / 3.9 s** |
| switching between two chats (30K and 15K) | 20-48 s (full re-read) | **0.3-1.6 s** |
| switching back to a 200K chat from a 5K one | ~47 s (full re-read) | **3.0-3.2 s** (from the SSD) |

Measured 2026-10-07 on the shipped config. In real use the evening before (an agent chat that grew to
200K tokens): follow-up turns read only the new 20-1,200 tokens and start answering in 0.2-3 s.

### By context depth

Fresh prompt of real text at each depth, then a 256-token answer (greedy, thinking off, `tools/depth_bench.py`),
each depth a new conversation:

| depth | prefill | the previous build (0.1.39, split 36) | decode | previous chat written to the SSD first |
| ---: | ---: | ---: | ---: | ---: |
| 2K | 553 tok/s | 516 tok/s | 170 tok/s | |
| 32K | 2,911-3,939 tok/s | 3,048 tok/s | 159-165 tok/s | |
| 62K | 4,040 tok/s | 3,982 tok/s | 150 tok/s | |
| 92K | 4,018 tok/s | 3,826 tok/s | 151 tok/s | 0.7 s |
| 122K | 3,924 tok/s | 2,366 tok/s | 149 tok/s | 0.9 s |
| 152K | 3,766 tok/s | 2,614 tok/s | 142 tok/s | 1.2 s |
| 182K | 3,741 tok/s | 3,163 tok/s | 140 tok/s | 6.8 s |
| 212K | 3,393 tok/s | 3,117 tok/s | 147 tok/s | 9.3 s |
| 242K | 3,552 tok/s | 2,707 tok/s | 139 tok/s | 13.2 s |
| 260K | 3,127 tok/s | 3,045 tok/s | 140 tok/s | 18.9 s |

Measured 2026-10-07 on the shipped config; the 260K prompt is read in 83 s (85 s before). The last
column is from the run before patch 20: back then a new conversation first wrote the one before it to
the SSD, and on this 94%-full drive those writes slowed to 170-360 MB/s after the first few GB, so the
260K prompt waited 18.9 s (102 s to its first token). Since patch 20 the write happens while the server
is idle, 2 s after the previous answer, and the next conversation finds the file already there. Prefill
above leaves the write out. The first 32K run, right after a quiet period, read at 1,933 tok/s.

Every run, A/B and rejected knob: [docs/benchmarks.md](docs/benchmarks.md).

## Requirements

- **GPUs:** an RTX 5090 (or another 32 GB Blackwell card) plus a 16 GB NVIDIA card; the second one can sit on a chipset x1 slot.
  The layer split (37) and the VRAM reserves are sized for exactly 32 + 16 GB.
- **RAM:** 32 GB plus zram swap. With the model up, about 1-2 GB stays available and some engine memory
  sits in zram. Headless box: no RAM or VRAM is left for a desktop.
- **Disk:** a fast NVMe with ~80 GB free for the model, plus up to 32 GB for conversations spilled to disk
  (`--conversation-spill-mib`, default 32768; the oldest file goes first).
- **Software:** Linux, NVIDIA driver, CUDA toolkit (`nvcc`), `cmake`, `ninja`, `git`, `patch`, Python 3.10+.

## Install

### 1. Build

```bash
./install.sh
```

- Clones upstream Strata at tag v0.1.40.1 into `./strata` and applies `patches/` in order
- Builds the engine and the vision helper for sm_89 + sm_120, creates the venv
- Checks the patched files against `patches/MANIFEST.sha256` (the tested tree)
- Safe to re-run

| Variable | Default | Purpose |
| --- | --- | --- |
| `MODELS` | `./models` | where the GGUF lives; written into the config |
| `JOBS` | `3` | parallel compile jobs (~3 GB of RAM each) |
| `CUDA_ARCHS` | `89;120` | GPU architectures to build |
| `STRATA_GGML_DIR` | | a local llama.cpp checkout at the pinned commit |

### 2. Download the model

```bash
strata/.venv/bin/pip install -U huggingface_hub
strata/.venv/bin/hf download ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF --include "IQ3_XXS/*" "mmproj-*" --local-dir models
mv models/IQ3_XXS/* models/ && rmdir models/IQ3_XXS
./prepare.sh
```

- Shard 1 (47 GB, the experts) is read in place; shard 2 (28.8 GB) is the PLE table
- `prepare.sh` builds the dense pack (`packs/gsq-iq3_xxs`) and the MTP draft runtime (`mtp/rt`) with Strata's own tools

### 3. Run

```bash
launchers/flash-next-262k.sh
```

- Serves `http://127.0.0.1:8888/v1`: OpenAI chat completions and Anthropic messages, model name `qwen3.8-flash-next`
- Overrides: `CONFIG=`, `PORT=`, `HOST=`
- Sampling defaults 0.6 / 0.95 / 20; per-request drafter tuning with `"strata_tune": {"spec_min_p": 0.8}`
- A `max_tokens` that no longer fits the context gets a shorter completion instead of a 400

> **No authentication.** `HOST=0.0.0.0` exposes the endpoint, image input included, to your whole network.
> Only do that behind a firewall rule or a proxy that adds auth.

## What is in the patch series

Each patch is one tested step, conflict resolutions included; applied to v0.1.40.1 they rebuild the tested tree byte for byte.

| # | Source | What it does |
| --- | --- | --- |
| 01 | PR #1122 | the asynchronous expert tier together with pipelined verify windows (0.1.40 otherwise turns `--adapt-async` off with them) |
| 02 | PR #1125 | AVX2 Q8_K quantizer for the CPU i-quant layers |
| 03 | PR #547 | the prompt path borrows 1.25 GiB fewer expert slots per 32K chunk |
| 04 | PR #567 | tokenise only the new turn of a conversation |
| 05 | PR #572 | an unfinished tool call comes back as content |
| 06 | ours | `--prefill-main`: every prompt read on the 5090; conversation parking with a layer split |
| 07 | ours | `STRATA_BLOB_PREAD=1`: one `pread` per cold expert instead of up to 500 page faults |
| 08 | ours | `STRATA_RESIDENT_LEND=1`: experts the prompt path borrows stay in locked RAM on a split |
| 09 | ours | split merged tool turns back into steps, so each step reads only the new result |
| 10 | PR #910 (parts) | bounded attention merge, `STRATA_MTP_KV`, pipelined decode with PLE prefetch (opt-in flags) |
| 11 | PR #958 | the fused prompt layout shrinks MoE buffers only when every layer can take the fused path |
| 12 | PR #1033 | short prompts gather GPU-resident experts in groups too |
| 13 | PR #1050 | `STRATA_PREFILL_CPU_SHARE=auto` (off by default) |
| 14 | PR #1090 | `--prefix-cache-dir`: system prompts saved to disk, keyed by the full config fingerprint |
| 15 | ours | the prefix cache under `--prefill-main` (the stage resyncs after a restore) |
| 16 | ours | merge fixes: two stray parentheses, one test updated for 0.1.40's prompt encoding |
| 17 | ours | `--conversation-spill-dir`: a conversation the RAM cache cannot park goes to the SSD; the Monitor page shows it |
| 18 | PR #1269 | a session file restores in 16 MiB blocks instead of being read into RAM whole |
| 19 | ours | the spill restores through 18 |
| 20 | ours | the spill is written while the engine is idle (a new request cancels it), and the files are deleted when the server stops |

Already in v0.1.40.1, so no longer patches: the RAM copy on a layer split (#848), pipelined verify windows
(#859), the asynchronous tier and pipelined decode (#876), CPU IQ kernels (#863), #510, #525 (and its
stranded-call rescue, now built in), #934, #1043, #1049. Left out: #904 (verify-window PDL; conflicts
with upstream's kernel rewrite, and decode is faster without it).
PR #439 (batched expert gathers) is left out on purpose: under `--prefill-main` it deadlocks on long prompts.
Details for every piece: [docs/how-it-works.md](docs/how-it-works.md).

## Tuning in the shipped config

| Setting | Why |
| --- | --- |
| `"layer_split": "37"` | layers 0-36 on the 5090, 37-47 + drafter on the 4070, which holds every expert of its layers; 37 gives the 5090 1,063 more cached experts than 36 (38 tested: fewer, slower 2K prompts) |
| `"vision": {"cuda_device": 1}` | the image encoder runs on the 4070 (1.28 GB there, 1.7 GB on the 5090), which is what makes room for split 37 |
| `--prefill auto:32768` | fewer chunks per prompt, so the experts stream fewer times |
| `--short-read 768` | new text up to 768 tokens goes through the decode windows (a 150-token message: 1.7 to 0.5 s) |
| `--conversation-cache-mib 1024`, 8 slots | parked chats survive the small side requests chat apps send; kept small so the engine has RAM |
| `--conversation-spill-dir conversation-spill` | a chat too big to park is written to the SSD (~16 KB per token) and read back from there |
| `--conversation-cache-min-free-mib 1024` | the default floor (2,560) refuses every park at headroom 4 |
| `--prefix-cache-dir prefix-cache` | a known system prompt is restored from disk (about 430 MB per 20K tokens) |
| `STRATA_SPLIT_SMALL_OWN=3072` | reads up to 3K tokens keep 986 cache slots: faster tool steps, decode 193 to 176 |
| `STRATA_RESIDENT_HEADROOM_GIB=4` | the RAM the lend region leaves free: every borrowed slot stays in locked RAM, so refilling them after a prompt takes 0.15 s instead of 6 s |
| `STRATA_PF_FUSED=1` | fused int8 tensor-core prompt kernels for the IQ packs (+9-13% on prompts) |
| `MALLOC_MMAP_THRESHOLD_`, `MALLOC_ARENA_MAX` | about 0.7 GB more available RAM, speed-neutral |
| `--kv int8` | the KV cache stays at 8 bits |

Headroom 4 assumes nothing else runs on the box: about 3.5 GB of engine memory goes to zram (5.6-6.8 GB
on the v0.1.39 build), and now and then a tool step stalls for a couple of seconds on page faults. Use 14 if you work on the
desktop while it serves (prompts ~40% slower, refills 6 s).

Parking 1024 MiB holds chats up to about 50K tokens. Anything longer is written to the spill directory
instead (a 200K chat is a 3.1 GB file, written in 1.6-2.5 s while the server is idle; a request that
arrives meanwhile cancels the write), and the file is kept after it is read back,
so the next switch reuses it while the chat is at most 8,192 tokens past it. Going back to a 200K chat
takes 3 s instead of the 47 s re-read it cost before. The files belong to one server run: they are
deleted when it stops and when it starts. With 64 GB of RAM raise the parking budget to 6144
or more.

## Tools

All talk to `127.0.0.1:8888` unless `STRATA_URL` is set.

| Script | Measures |
| --- | --- |
| `tools/bench.py NAME` | 5 decodes, 2K / 16K / 80K fresh prompts, a follow-up (one JSON line) |
| `tools/depth_bench.py` | the depth table above |
| `tools/step_times.py NAME TEXTFILE` | tool-result sized reads on real text |
| `tools/decode_after.py NAME` | decode right after a big prompt |
| `tools/needle_followups.py` | 40K needle, four follow-ups, a 20K extension |
| `tools/parking_check.py` | two alternating conversations: correctness and switch time |
| `tools/spill_check.py` | a 200K and a 5K conversation alternating: the spill to disk and back |
| `tools/merged_tool_turn.py` | a client that merges a turn's tool calls (`OLD_IDS=1` shows the re-reads patch 13 removes) |
| `tools/spec_min_p_sweep.py NAME` | per-request drafter threshold A/B, no restart |
| `tools/snapshot.py` | page faults, swap, direct reclaim, NVMe, GPU counters; diff them around a run |

## Status

- The patch series is checked in CI against a pristine v0.1.40.1 checkout.
- `install.sh` and `prepare.sh` have not been run end to end from a clean checkout yet; reports welcome.

## License

MIT ([LICENSE](LICENSE)). Strata is MIT ([LICENSE.strata](LICENSE.strata)).
