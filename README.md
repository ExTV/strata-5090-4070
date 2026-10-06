# strata-5090-4070

> Qwen3.8-Flash-Next with the **full 262,144-token context** on an RTX 5090 + RTX 4070 Ti SUPER and 31 GB of RAM.

<p>
  <a href="https://github.com/ExTV/strata-5090-4070/actions/workflows/patches-apply.yml"><img src="https://github.com/ExTV/strata-5090-4070/actions/workflows/patches-apply.yml/badge.svg" alt="patches apply"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
</p>

A patched build of [Strata](https://github.com/Niko1221/Strata) for one specific box:
a 32 GB card, a 16 GB card in a chipset x1 slot, and less RAM than the 47 GB expert file.

- **Upstream Strata v0.1.39** plus 25 patches: Hardin22's two-GPU PRs, twelve other open PRs, four of our own
- **179 tok/s decode**, prompts up to **3,982 tok/s**, a 260K-token prompt read in **85 s**
- Decode never touches the SSD: the experts no card holds sit page-locked in RAM
- Switching between conversations restores the parked one in **0.5-1 s**
- A new chat with a system prompt seen before restores it from disk instead of reading it (**0.6 s** vs 11.7 s for 20K tokens)
- Agent-friendly: a 2.7K-token tool result is answered in **3.6 s**; three tool-call shapes fixed, merged tool turns split
- OpenAI and Anthropic compatible API on `:8888`, images on

## Quick start

```bash
git clone https://github.com/ExTV/strata-5090-4070.git && cd strata-5090-4070
./install.sh                    # clone Strata v0.1.39, apply patches, build engine + vision helper, venv
# download the model (step 2 below), then:
./prepare.sh                    # dense pack + MTP drafter
launchers/flash-next-262k.sh    # serves http://127.0.0.1:8888/v1
```

[Benchmarks](docs/benchmarks.md) · [How it works](docs/how-it-works.md) · [Issues](https://github.com/ExTV/strata-5090-4070/issues)

## Performance

### Against stock Strata on the same box

| | stock Strata 0.1.33, split 36 | this repo |
| --- | --- | --- |
| decode, 600-token answers, greedy | 99-111 tok/s | **179 tok/s** |
| 2K fresh prompt | 200-240 tok/s | **492-565 tok/s** |
| 16K fresh prompt | 470-646 tok/s | **2,020 tok/s** |
| 27K fresh prompt of real text | | **2,842 tok/s** (9.5 s) |
| 80K fresh prompt | 886-928 tok/s | **2,743 tok/s** |
| tool results of 1.6K / 2.9K / 4.2K tokens | | **3.4 / 3.6 / 4.0 s** |
| switching between two chats (30K and 15K) | 20-48 s (full re-read) | **0.5-1.1 s** |

In real use (an agent chat that grew to 200K tokens): follow-up turns read only the new 20-1,200
tokens and start answering in 0.2-3 s, decode stays at 124-190 tok/s, and a full re-read of 175K
tokens takes 47 s.

### By context depth

Fresh prompt of real text at each depth, then a 256-token answer (greedy, thinking off, `tools/depth_bench.py`):

| depth | prefill | prefill, headroom 14 (2026-10-05) | decode |
| ---: | ---: | ---: | ---: |
| 2K | 516 tok/s | 579 tok/s | 156 tok/s |
| 32K | 3,048 tok/s | 1,742 tok/s | 141 tok/s |
| 62K | 3,982 tok/s | 2,503 tok/s | 136 tok/s |
| 92K | 3,826 tok/s | 2,727 tok/s | 136 tok/s |
| 122K | 2,366 tok/s | 2,792 tok/s | 133 tok/s |
| 152K | 2,614 tok/s | 2,727 tok/s | 128 tok/s |
| 182K | 3,163 tok/s | 3,116 tok/s | 136 tok/s |
| 212K | 3,117 tok/s | 3,131 tok/s | 132 tok/s |
| 242K | 2,707 tok/s | 3,169 tok/s | 127 tok/s |
| 260K | 3,045 tok/s | 3,269 tok/s | 128 tok/s |

Measured 2026-10-06 on the shipped config (headroom 4). From 32K to 92K prompts read 40-75% faster than with
headroom 14; past that the two are within noise of each other or a little slower (the 260K prompt took
85.3 s against 79.5), because those prompts borrow more slots than locked RAM covers either way and the
engine has less RAM to work with.

Every run, A/B and rejected knob: [docs/benchmarks.md](docs/benchmarks.md).

## Requirements

- **GPUs:** an RTX 5090 (or another 32 GB Blackwell card) plus a 16 GB NVIDIA card; the second one can sit on a chipset x1 slot.
  The layer split (36) and the VRAM reserves are sized for exactly 32 + 16 GB.
- **RAM:** 32 GB plus zram swap. With the model up, about 1-2 GB stays available and some engine memory
  sits in zram. Headless box: no RAM or VRAM is left for a desktop.
- **Disk:** a fast NVMe with ~80 GB free for the model.
- **Software:** Linux, NVIDIA driver, CUDA toolkit (`nvcc`), `cmake`, `ninja`, `git`, `patch`, Python 3.10+.

## Install

### 1. Build

```bash
./install.sh
```

- Clones upstream Strata at tag v0.1.39 into `./strata` and applies `patches/` in order
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

Each patch is one tested step, conflict resolutions included; applied to v0.1.39 they rebuild the tested tree byte for byte (patch 25 leaves out one PNG in upstream's docs).

| # | Source | What it does |
| --- | --- | --- |
| 01 | PR #848 | the page-locked RAM copy of the experts works with a layer split |
| 02 | PR #859 | pipelined verify windows: the 5090 runs window K+1 while the 4070 verifies K |
| 03 | PR #851 | AVX2 Q8_K quantizer |
| 04 | PR #863 | CPU IQ kernels |
| 05 | PR #547 | the prompt path borrows 1.25 GiB fewer expert slots per 32K chunk |
| 06 | PR #567 | tokenise only the new turn of a conversation |
| 07 | PR #510 | malformed tool arguments in history |
| 08 | PR #572 | an unfinished tool call comes back as content |
| 09 | PR #525 | a tool call stranded in an unclosed thinking span |
| 10 | ours | `--prefill-main`: every prompt read on the 5090; conversation parking with a layer split |
| 11 | ours | `STRATA_BLOB_PREAD=1`: one `pread` per cold expert instead of up to 500 page faults |
| 12 | ours | `STRATA_RESIDENT_LEND=1`: experts the prompt path borrows stay in locked RAM on a split |
| 13 | ours | split merged tool turns back into steps, so each step reads only the new result |
| 14 | PRs #876 #905 #910 | asynchronous expert tier, pipelined decode, fork parity |
| 15 | PR #904 | verify-window PDL and graph branches |
| 16 | PR #904 (update) | `STRATA_DF_BRANCH` opt-in: graph branches plus NVML queries could stall a window on Linux |
| 17 | PR #910 (update) | `STRATA_ATTN_MERGE_V2` opt-in |
| 18 | PR #525 (update) | stranded-call rescue: opener must start a line outside a code fence, declared tools only |
| 19 | PR #958 | the fused prompt layout shrinks MoE buffers only when every layer can take the fused path |
| 20 | PR #1049 | the fused SwiGLU q8_1 quantizers keep scales finite |
| 21 | PR #1043 | residency-table uploads finish before other streams read the table |
| 22 | PR #1033 | short prompts gather GPU-resident experts in groups too |
| 23 | PR #1050 | `STRATA_PREFILL_CPU_SHARE=auto` (off by default); ours: also under `--prefill-main` |
| 24 | PR #960 | `--prefix-cache-dir`: system prompts saved to disk; ours: works under `--prefill-main` |
| 25 | PR #934 | `--expert-cache-per-layer` (off: faster prompts, but decode 102 tok/s here) |

PR #439 (batched expert gathers) is left out on purpose: under `--prefill-main` it deadlocks on long prompts.
Details for every piece: [docs/how-it-works.md](docs/how-it-works.md).

## Tuning in the shipped config

| Setting | Why |
| --- | --- |
| `"layer_split": "36"` | layers 0-35 on the 5090, 36-47 + drafter on the 4070, which then holds every expert of its layers |
| `--prefill auto:32768` | fewer chunks per prompt, so the experts stream fewer times |
| `--short-read 768` | new text up to 768 tokens goes through the decode windows (a 150-token message: 1.7 to 0.5 s) |
| `--conversation-cache-mib 3072`, 8 slots | parked chats survive the small side requests chat apps send |
| `--conversation-cache-min-free-mib 1024` | the default floor (2,560) refuses every park at headroom 4 |
| `--prefix-cache-dir prefix-cache` | a known system prompt is restored from disk (about 430 MB per 20K tokens) |
| `STRATA_SPLIT_SMALL_OWN=3072` | reads up to 3K tokens keep 986 cache slots: faster tool steps, decode 193 to 176 |
| `STRATA_RESIDENT_HEADROOM_GIB=4` | the RAM the lend region leaves free: every borrowed slot stays in locked RAM, so refilling them after a prompt takes 0.15 s instead of 6 s |
| `STRATA_PF_FUSED=1` | fused int8 tensor-core prompt kernels for the IQ packs (+9-13% on prompts) |
| `MALLOC_MMAP_THRESHOLD_`, `MALLOC_ARENA_MAX` | about 0.7 GB more available RAM, speed-neutral |
| `--kv int8` | the KV cache stays at 8 bits |

Headroom 4 assumes nothing else runs on the box: about 6 GB of engine memory goes to zram, and roughly
one tool step in nine stalls for a couple of seconds on page faults. Use 14 if you work on the
desktop while it serves (prompts ~40% slower, refills 6 s).

Parking 3072 MiB holds chats up to about 160K tokens (a snapshot is ~19.5 KB per token). A longer chat cannot park (its snapshot is
3.3-3.7 GB), so if a second conversation or a client's side request runs in between, going back to the
long chat re-reads it (~47 s for 175K). With 64 GB of RAM raise the parking budget to 6144 or more.

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
| `tools/merged_tool_turn.py` | a client that merges a turn's tool calls (`OLD_IDS=1` shows the re-reads patch 13 removes) |
| `tools/spec_min_p_sweep.py NAME` | per-request drafter threshold A/B, no restart |
| `tools/snapshot.py` | page faults, swap, direct reclaim, NVMe, GPU counters; diff them around a run |

## Status

- The patch series is checked in CI against a pristine v0.1.39 checkout.
- `install.sh` and `prepare.sh` have not been run end to end from a clean checkout yet; reports welcome.

## License

MIT ([LICENSE](LICENSE)). Strata is MIT ([LICENSE.strata](LICENSE.strata)).
