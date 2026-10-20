# strata-5090-4070

> Qwen3.8-Flash-Next with the **full 262,144-token context** on an RTX 5090 + RTX 4070 Ti SUPER and 31 GB of RAM.

<p>
  <a href="https://github.com/ExTV/strata-5090-4070/actions/workflows/patches-apply.yml"><img src="https://github.com/ExTV/strata-5090-4070/actions/workflows/patches-apply.yml/badge.svg" alt="patches apply"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
</p>

A patched build of [Strata](https://github.com/Niko1221/Strata) for one specific box:
a 32 GB card, a 16 GB card in a chipset x1 slot, and less RAM than the expert file. This is the
exact setup that serves my own agents every day; what is here is what runs.

- **Upstream Strata v0.1.41** plus 13 patches: the dual-GPU series, four open upstream PRs, two upstream commits and our own work
- **ISTA GSQ-RCO IQ3_S** (the quality tier that still keeps every decode expert off the SSD here), with the
  IQ3_XXS config kept as the faster alternative
- **160-200 tok/s decode** on IQ3_S (code 237, reasoning 194, prose 146 tok/s at temperature 0), prompts up to
  **3,480 tok/s**, a 260K-token prompt read in **76 s**
- Decode never touches the SSD: the experts no card holds sit page-locked in RAM
- Switching between conversations restores the parked one in **0.7-1.4 s**; a 200K conversation too big
  to park goes to the SSD and comes back in **2.8-2.9 s** instead of a 61 s re-read
- The image encoder runs on the 4070, so the 5090 keeps more experts; the draft layer's prompt K/V is computed
  on the 5090 too, so long prompts no longer wait on the x1 link
- Agent-friendly: tool calls parsed **44/60** on a probe that edits a file documenting the call format (21/60
  with the stock template and parser), merged tool turns split, a 2.7K-token tool result answered in **3.6 s**
- The refusal direction is projected out at runtime (a 480 KB control vector, the weights untouched)
- OpenAI and Anthropic compatible API on `:8888`, images on

## Quick start

```bash
git clone https://github.com/ExTV/strata-5090-4070.git && cd strata-5090-4070
./install.sh                    # clone Strata v0.1.41, apply patches, build engine + vision helper, venv
# download the model (step 2 below), then:
./prepare.sh                    # dense pack + MTP drafter + the Sharp chat template at xhigh
launchers/flash-next-262k.sh    # serves http://127.0.0.1:8888/v1
```

[Benchmarks](docs/benchmarks.md) · [How it works](docs/how-it-works.md) · [Issues](https://github.com/ExTV/strata-5090-4070/issues)

## Performance

### The shipped config (IQ3_S) and the IQ3_XXS alternative

Same engine, same settings except the quant and its prompt chunk, measured 2026-10-10 on this box
(`tools/bench.py`, `tools/depth_bench.py`, `tools/step_times.py`; the probes and the tool-call runs on the
dates given in [docs/benchmarks.md](docs/benchmarks.md)):

| | **IQ3_S (shipped)** | IQ3_XXS (`strata-flash-next-iq3xxs-262k.json`) |
| --- | --- | --- |
| experts in the two GPU caches | 18,620 of 24,576 | 21,752 of 24,576 |
| decode, 600-token answers, greedy, median | **168-198 tok/s** | 181-203 tok/s |
| 2K / 16K / 80K fresh prompt | 3.7 / 7.2 / 25.9 s | 3.4-3.6 / 6.6 / 21.1 s |
| 2K follow-up on the 80K chat | 6.6 s | 3.9 s |
| 32K / 122K / 260K prompt of real text | 10.2 / 35.1 / 76.4 s (3,124 / 3,479 / 3,405 tok/s) | 10.2 / 32.3 / 76 s |
| decode after those depths | 135 / 131 / 124 tok/s | 159-165 / 149 / 140 tok/s |
| tool-result steps of 1.5K / 2.3K / 5.4K tokens | 3.2-3.6 / 3.4-3.6 / 3.8-4.2 s | 3.0 / 3.2 / 3.9 s |
| SSD reads during decode | 0 | 0 |
| draft acceptance | 84.5% | 81-86% |
| KL divergence from BF16 (sirfyyn, three corpora) | 0.069 / 0.061 / 0.183 | 0.118 / 0.112 / 0.264 |
| ISTA's task average (BF16: 93.12) | 93.26 | 92.57 |

The IQ3_XXS numbers are from the same day on the same build; the IQ3_XXS history below and in the docs is
how the build got here. Quants that did not make it: ISTA Q2_0 (211 tok/s, all experts resident, lower
quality), unsloth UD-IQ4_XS (58 tok/s: its 15,340 resident experts leave decode reading the SSD on 31 GB).

### Against stock Strata on the same box (IQ3_XXS, 2026-10-07)

| | stock Strata 0.1.33, split 36 | this build, IQ3_XXS |
| --- | --- | --- |
| decode, 600-token answers, greedy | 99-111 tok/s | **188-205 tok/s** |
| 2K fresh prompt | 200-240 tok/s | **597-655 tok/s** |
| 16K fresh prompt | 470-646 tok/s | **2,117-2,315 tok/s** |
| 80K fresh prompt | 886-928 tok/s | **3,146-3,359 tok/s** |
| 2K follow-up on the 80K chat | 7.9 s | **3.8-4.6 s** |
| switching between two chats (30K and 15K) | 20-48 s (full re-read) | **0.3-1.6 s** |
| switching back to a 200K chat from a 5K one | ~47 s (full re-read) | **3.0-3.2 s** (from the SSD) |

### Tool calls (2026-10-15, IQ3_S)

`tools/tool_probe.py`, 60 two-turn sequences: parallel `read_file` calls with integer arguments, then an
`edit_file` whose strings contain a literal `<parameter=limit>..</parameter>` line, plus a `bash` call.

| template / parser | pass | what failed |
| --- | --- | --- |
| stock Qwen template, stock parser | 21/60 | |
| Sharp template at its medium default | 8/60 | the edit's `new_string` empty in 15 |
| Sharp at xhigh (shipped), stock parser | 30-33/60 | 17 edits cut at the nested `</parameter>`, 14 `bash` calls never written |
| **Sharp at xhigh, patch 08** | **44/60** | 9 `bash` calls never written, 5 `new_string` never written, 2 turns ended inside the thinking |

Every remaining miss is the model's: the raw engine output shows the call was never written. The model also
writes `<parameter=limit>25</parameter>` and then skips the value's own closer in about half of these edits;
patch 08 reads that correctly, which is the 17 -> 0.

Every run, A/B and rejected knob: [docs/benchmarks.md](docs/benchmarks.md).

## Requirements

- **GPUs:** an RTX 5090 (or another 32 GB Blackwell card) plus a 16 GB NVIDIA card; the second one can sit on a chipset x1 slot.
  The layer split (39) and the VRAM reserves are sized for exactly 32 + 16 GB.
- **RAM:** 32 GB plus zram swap. With the model up, about 1-2 GB stays available and some engine memory
  sits in zram. Headless box: no RAM or VRAM is left for a desktop.
- **Disk:** a fast NVMe with ~85 GB free for IQ3_S (55 GB of experts + 29 GB of PLE table), ~77 GB for IQ3_XXS
  (the PLE shard is the same file), plus up to 32 GB for conversations spilled to disk
  (`--conversation-spill-mib`, default 32768; the oldest file goes first).
- **Software:** Linux, NVIDIA driver, CUDA toolkit (`nvcc`), `cmake`, `ninja`, `git`, `patch`, `curl`, Python 3.10+.

## Install

### 1. Build

```bash
./install.sh
```

- Clones upstream Strata at tag v0.1.41 into `./strata` and applies `patches/` in order
- Builds the engine and the vision helper for sm_89 + sm_120, creates the venv
- Writes `strata/strata-flash-next-262k.json` (IQ3_S) and `strata/strata-flash-next-iq3xxs-262k.json`
- Checks the patched files against `patches/MANIFEST.sha256` (the tested tree)
- Safe to re-run

| Variable | Default | Purpose |
| --- | --- | --- |
| `MODELS` | `./models` | where the GGUF lives; written into the configs |
| `JOBS` | `3` | parallel compile jobs (~3 GB of RAM each) |
| `CUDA_ARCHS` | `89;120` | GPU architectures to build |
| `STRATA_GGML_DIR` | | a local llama.cpp checkout at the pinned commit |

### 2. Download the model

```bash
strata/.venv/bin/pip install -U huggingface_hub
strata/.venv/bin/hf download ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF --include "IQ3_S/*" "mmproj-*" --local-dir models
strata/.venv/bin/hf download alesha-pro/Qwen3.8-Flash-Next-abliterated-GSQ-RCO-Strata-GGUF Huihui-Qwen3.8-Flash-Next-refusal-direction-r.gguf --local-dir models
./prepare.sh
```

- Shard 1 (55 GB, the experts) is read in place; shard 2 (28.8 GB) is the PLE table. For the IQ3_XXS config
  download `"IQ3_XXS/*"` as well (its shard 2 is the same bytes) and run `QUANT=IQ3_XXS ./prepare.sh`
- The control vector (480 KB) is the refusal direction of huihui-ai's abliterated release, applied at runtime;
  leave the four `--control-vector*` / `--cvec*` arguments out of the config for the stock model
- `prepare.sh` builds the dense pack (`packs/gsq-iq3_s`), the MTP draft runtime (`mtp/rt`) with Strata's own
  tools, and `packs/gsq-iq3_s/tokenizer-sharp`: the pack's tokenizer with the
  [Sharp chat template](https://huggingface.co/peculiar-ragdoll/Qwen-Sharp-Chat-Templates) v22.5.0 (Apache-2.0,
  fetched at a pinned revision and checked) and its default reasoning effort raised from medium to xhigh

### 3. Run

```bash
launchers/flash-next-262k.sh
```

- Serves `http://127.0.0.1:8888/v1`: OpenAI chat completions and Anthropic messages, model name `qwen3.8-flash-next`
- Overrides: `CONFIG=strata-flash-next-iq3xxs-262k.json` for the IQ3_XXS config, `PORT=`, `HOST=`
- Sampling defaults 0.6 / 0.95 / 20; per-request drafter tuning with `"strata_tune": {"spec_min_p": 0.8}`
- A `max_tokens` that no longer fits the context gets a shorter completion instead of a 400
- Reasoning effort: the template defaults to xhigh; a request's `reasoning_effort` (`none` .. `xhigh`) or
  `chat_template_kwargs.enable_thinking: false` overrides it

> **No authentication.** `HOST=0.0.0.0` exposes the endpoint, image input included, to your whole network.
> Only do that behind a firewall rule or a proxy that adds auth.

## What is in the patch series

Each patch is one tested step, conflict resolutions included; applied to v0.1.41 they rebuild the tested tree
byte for byte (62 files, `patches/MANIFEST.sha256`).

| # | Source | What it does |
| --- | --- | --- |
| 01 | ours + 10 PRs | the whole series of the previous release (v0.1.40.1 + 20 patches) merged onto v0.1.41: `--prefill-main` with conversation parking on a layer split, `pread` expert copies, the lend region in locked RAM, merged tool turns split into steps, the prefix cache under `--prefill-main`, conversations spilled to the SSD and restored in 16 MiB blocks, the idle spill write, plus the open PRs of that series (#1122, #1125, #547, #567, #572, #910 parts, #958, #1033, #1050, #1090, #1269) |
| 02 | ours | merge fix: `prefill.cpp` keeps #547's `bytes_needed` source flag and the docs keep the prefill-main notes |
| 03 | PR #1599 | `STRATA_SPLIT_MTP_BATCH=1`: the draft layer's prompt K/V computed in batches on the drafter's stage (opt-in; inert under `--prefill-main`, which is why 04 exists) |
| 04 | ours | `STRATA_PM_MTP_BATCH=1`: under `--prefill-main` the draft layer's prompt K/V is computed on the 5090 and only the K/V rows cross the x1 link to the 4070 (an 82K prompt: 4.0-4.3 s of link traffic per chunk -> 0.3 s; 32K TTFT 9.9 -> 9.0 s, 82K 21.3 -> 16.8 s) |
| 05 | PR #2265, v0.1.42, PR #1838 | `--conversation-cache-park-gain N`: a conversation is parked again only once it grew N tokens (before: every turn wrote a whole snapshot the next turn dropped, 294 GB over one day's log); `STRATA_ROUTE_TAIL_SKIP` (upstream's 0.1.42 default: a missed expert every token of a window routes at rank 7+ is skipped, ms per window 13.2 -> 12.8 here); `STRATA_RAM_ADAPT=N` (opt-in: the RAM copy follows the conversation between requests; does nothing on IQ3_S, +15-20% decode on the SSD-bound unsloth quant) |
| 06 | PR #2589 | `STRATA_SLOT_EXPIRE_S`: with `"parallel"` batch slots a short side request takes the slot whose conversation is cheapest to lose (inert without `"parallel"`) |
| 07 | PR #2572 | with `"tool_call_recovery": true` a parameter written `<parameter name="X">` or as one JSON `<parameter>` keeps its value (off in the shipped config: this model never writes those forms, and recovery invented a call in 1 of 60 runs) |
| 08 | ours | the tool-call parser tracks nested `<parameter=..>...</parameter>` pairs inside a value and reads the closer the model skips after one (`<parameter=limit>25</parameter>` then straight to `</function>`): 17 of 60 cut edits -> 0 |
| 09 | upstream 6f3e3810 (v0.1.44) | `STRATA_COMMIT_BATCH` (default on): the commit of the accepted tokens into every GDN and attention layer's state in one launch per layer kind instead of ~100 graph nodes; bitwise, ~1% of the window here, 5% at 20K context |
| 10 | upstream d3fb3e6f (v0.1.42), ported | the layer split's streamed-ring size is decided before the lend regions are sized, plus a start line with borrowed vs RAM-kept slots; inert on this config (the sizing already matched), carried for the line and the next rebase |
| 11 | ours | `--kv-resident-later N`: the later stages' own `--kv-resident`; `0` keeps the whole K/V of the 4070's three attention layers in VRAM with no pinned copy, so nothing is read over the x1 link during decode (the session copy between a streamed and a resident state is new) |
| 12 | ours | `--prefill-main-small S` / `--prefill-main-small-max M`: under `--prefill-main` every text prompt part up to M tokens (the shipped config: the whole context) is read split-wise: the 5090 runs its own layers out of its expert cache in its usual chunks and hands each chunk whole to the 4070 through one 640 MiB pinned buffer, and the 4070 runs its nine layers from its resident experts in S-token pieces while the 5090 reads the next chunk; a part is cut into ~4 chunks so short ones pipeline too. Before, every part past `--short-read` was read whole-model on the 5090, which streamed the 4070's layers' experts from the SSD for every 16K chunk (57 GB per 81K prompt): fresh 13K / 16K / 32K / 64K / 81K / 203K prompts 13.4 / 6.4 / 10.6 / 19.0 / 24-25 / 57.7 s -> 4.0 / 5.0 / 8.6 / 15.9 / 18.5-20 / 41 s, agent steps 3.3 / 6.5 / 3.9 -> 1.1 / 1.2 / 1.8 s, SSD reads ~0; the 4070 keeps a 512-token path (644 MiB, reserve 700 -> 420 MiB); also holds the draft head back from the later card's expert room, which the sizing had missed |
| 13 | ours | the draft layer's K/V projections (28 MiB) are copied to the 5090 at load, before the expert cache takes its VRAM; before, `STRATA_PM_MTP_BATCH=1` copied them on the first whole-model prompt (an image part) and the engine died when the 5090 was already full. If the copy cannot be made, prompts fall back to the drafter's own pass on the 4070 instead of failing |

Already in v0.1.41 and no longer carried: the fork's RAM copy, pipelined windows and asynchronous tier, the
CPU IQ kernels, #510, #525, #934, #1043, #1049. Left out: #904 (verify-window PDL; conflicts with upstream's
kernel rewrite, decode is faster without it), PR #439 (batched expert gathers; deadlocks under
`--prefill-main`), #2058 / #2059 (opt-in decode kernels, +3% slower here), #1598 / #1525 (neutral).
Details for every piece: [docs/how-it-works.md](docs/how-it-works.md).

## Tuning in the shipped config

| Setting | Why |
| --- | --- |
| `"layer_split": "39"` | layers 0-38 on the 5090, 39-47 + drafter on the 4070, which holds every expert of its layers. 39 since 2026-10-15 evening, together with the resident K/V below (alone it equals 38); 37 -> 38 earlier that day was -2% per verify window |
| `--kv-resident-later 0` | patch 11: the 4070 keeps the whole K/V of its attention layers in VRAM (+0.7 GB there, 0.8 GB of pinned RAM back): decode after 81-203K prompts +6-9%, 203K prefill 61.9 -> 57.2 s, 81K 24.5-29 -> 23-24 s; short prompts +0.2 ms per window (1.5-2.5%) |
| `"vision": {"cuda_device": 1}` | the image encoder runs on the 4070 (1.28 GB there, 1.7 GB on the 5090), which is what makes room for the split |
| `--prefill auto:16384` | IQ3_S has 3,000 fewer GPU-resident experts than IQ3_XXS; with 16K chunks every lent slot stays in locked RAM (32K: 41% of a chunk's loan re-read from the file); speed a wash, RAM cleaner. The IQ3_XXS config keeps 32768 |
| `STRATA_PM_MTP_BATCH=1` | patch 04: the draft layer's prompt K/V on the 5090 (long prompts -20..25% TTFT) |
| `--mtp-hnorm stream` | upstream's opt-in drafter norm (one RMS per hyper-connection stream instead of one over all four); on since 2026-10-13 together with the park gain, not A/B'd on its own |
| `--conversation-cache-park-gain 4096` | park again only after 4,096 new tokens: no snapshot churn on a long single conversation |
| `--control-vector-scaled FILE:1.0 --control-vector-layer-range 4 44 --cvec-mode project --cvec-dir per-layer` | the refusal direction projected out of the residual stream at runtime; speed-neutral, the weights are ISTA's own; `"experimental_speed_projection": false` in a request turns it off |
| `"tokenizer": ".../tokenizer-sharp"` | the Sharp template at xhigh: tool probe 33/60 vs 21/60 stock, short answers in a third of the tokens; at its medium default it dropped to 8/60, so effort is what matters |
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

`STRATA_ROUTE_TAIL_SKIP` is on by default in this build (patch 05, upstream's 0.1.42 default): answers differ
slightly from 0.1.41's bytes (upstream measured KL 0.003-0.006); `"STRATA_ROUTE_TAIL_SKIP": "0"` in the config's
`env` restores them.

Headroom 4 assumes nothing else runs on the box: about 3.5 GB of engine memory goes to zram, and now and then
a tool step stalls for a couple of seconds on page faults. Use 14 if you work on the desktop while it serves
(prompts ~40% slower, refills 6 s). Booting with a browser open cut the RAM expert tier from 16.4 to 5.2 GiB
once and decode to a third: the tier is sized at boot.

Parking 1024 MiB holds chats up to about 50K tokens. Anything longer is written to the spill directory
instead (a 200K chat is a 3.1 GB file, written in 1.6-2.5 s while the server is idle; a request that
arrives meanwhile cancels the write), and the file is kept after it is read back,
so the next switch reuses it while the chat is at most 8,192 tokens past it. The files belong to one server
run: they are deleted when it stops and when it starts. With 64 GB of RAM raise the parking budget to 6144
or more.

## Tools

All talk to `127.0.0.1:8888` unless `STRATA_URL` is set.

| Script | Measures |
| --- | --- |
| `tools/bench.py NAME` | 5 decodes, 2K / 16K / 80K fresh prompts, a follow-up (one JSON line) |
| `tools/depth_bench.py` | the depth rows above |
| `tools/step_times.py NAME TEXTFILE` | tool-result sized reads on real text |
| `tools/decode_after.py NAME` | decode right after a big prompt |
| `tools/window_bench.py [TAG]` | the A/B gate for engine changes: ms per verify window over 7 short prompts and a 20K one, one line appended to `window-bench.jsonl` |
| `tools/paired_ab.py TEMP ARM...` | per-request settings paired on one boot with a settle request and rotated order (see docs/how-it-works.md, measuring) |
| `tools/tool_probe.py [N] [TAG]` | the two-turn agent tool-call probe (`MODEL=`, `EFFORT=` to send `reasoning_effort`) |
| `tools/needle_followups.py` | 40K needle, four follow-ups, a 20K extension |
| `tools/parking_check.py` | two alternating conversations: correctness and switch time |
| `tools/spill_check.py` | a 200K and a 5K conversation alternating: the spill to disk and back |
| `tools/merged_tool_turn.py` | a client that merges a turn's tool calls (`OLD_IDS=1` shows the re-reads the split removes) |
| `tools/spec_min_p_sweep.py NAME` | per-request drafter threshold A/B, no restart |
| `tools/agent_steps.py TAG [SEED]` | a 13K first message and four tool-result follow-ups (1.5K / 2.4K / 5.4K / 0.5K tokens): prompt seconds and SSD GB per step (the patch 12 gate; `NVME=` names the device) |
| `tools/snapshot.py` | page faults, swap, direct reclaim, NVMe, GPU counters; diff them around a run |

## Status

- The patch series is checked in CI against a pristine v0.1.41 checkout.
- Upstream is at v0.1.44.1 (2026-10-14); a merge of this tree onto it conflicts in 8 files and nothing in
  0.1.42-0.1.44 changes decode on NVIDIA, so the rebase waits. The pieces of those releases worth having
  (the park gain, the tail skip) are carried as patch 05.
- `install.sh` and `prepare.sh` have not been run end to end from a clean checkout yet; reports welcome.

## License

MIT ([LICENSE](LICENSE)). Strata is MIT ([LICENSE.strata](LICENSE.strata)). The Sharp chat template that
`prepare.sh` downloads is Apache-2.0 (peculiar-ragdoll); the control vector is from alesha-pro's release.
