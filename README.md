# strata-5090-4070

> Qwen3.8-Flash-Next with the **full 262,144-token context** on an RTX 5090 + RTX 4070 Ti SUPER and 31 GB of RAM.

<p>
  <a href="https://github.com/ExTV/strata-5090-4070/actions/workflows/patches-apply.yml"><img src="https://github.com/ExTV/strata-5090-4070/actions/workflows/patches-apply.yml/badge.svg" alt="patches apply"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
</p>

A patched build of [Strata](https://github.com/Niko1221/Strata) for one specific box:
a 32 GB card, a 16 GB card in a chipset x1 slot, and less RAM than the expert file. This is the
exact setup that serves my own agents every day; what is here is what runs.

- **Upstream Strata v0.2.1** plus 8 patches: our dual-GPU series merged onto it, upstream PRs and commits it
  does not have yet, and our own fixes
- **Unsloth V3.1 UD-IQ3_XXS** with Unsloth's Q8_0 PLE table (the shipped config since 2026-11-04); the ISTA
  GSQ-RCO IQ3_S and IQ3_XXS configs are kept
- **250 tok/s decode** median over short answers (10.2 ms per verify window), 174 tok/s mean inside a
  conversation grown to 256K tokens; fresh prompts: 20K in **10.3 s**, 80K in **15.4 s**, 250K in **46.7 s**
- Decode never touches the SSD: the experts no card holds sit page-locked in RAM, and so does every cache slot
  the prompt path borrows, so a 250K prompt reads 14 GB from the SSD instead of 133 GB
- A conversation grown turn by turn to 256K tokens answers every turn in **2.0-2.5 s** with nothing swapped out
  on 31 GB of RAM (no parking, spill or prefix store in this config; the IQ3_S config still has them)
- The image encoder runs on the 4070, so the 5090 keeps more experts; the draft layer's prompt K/V is computed
  on the 5090 too, so long prompts no longer wait on the x1 link
- Agent-friendly: tool calls parsed **44/60** on a probe that edits a file documenting the call format (21/60
  with the stock template and parser), merged tool turns split, agent follow-up turns answered in **0.8-1.8 s**
- Images read split-wise too: an OCR crop in **1.2 s** instead of 5.1 s, with ~0 GB read from the SSD instead of 10 GB
- The refusal direction is projected out at runtime (a 480 KB control vector, the weights untouched)
- OpenAI and Anthropic compatible API on `:8888`, images on

## Quick start

```bash
git clone https://github.com/ExTV/strata-5090-4070.git && cd strata-5090-4070
./install.sh                    # clone Strata v0.2.1, apply patches, build engine + vision helper, venv
# download the model (step 2 below), then:
./prepare.sh                    # dense pack, MTP drafter, the Sharp chat template at xhigh, the Q8_0 PLE table
launchers/flash-next-262k.sh    # serves http://127.0.0.1:8888/v1
```

[Benchmarks](docs/benchmarks.md) · [How it works](docs/how-it-works.md) · [Issues](https://github.com/ExTV/strata-5090-4070/issues)

## Performance

### The shipped config (UD-IQ3_XXS, 2026-11-10, fresh boot at the login screen)

`tools/window_bench.py` (7 short answers of 600 tokens and one 20K prompt, thinking off, temperature 0),
`tools/prompt_bench.py` (fresh random-word prompts with a needle) and `tools/grow_chat.py` (one conversation
grown to the context limit). "Before" is the same build and model with the 2026-11-04 settings
(`--prefill auto:8192`, RAM budget 13.2 GiB, no thread placement), measured the same day.

| | Before | Shipped |
| --- | --- | --- |
| decode, ms per verify window (median of 7) | 11.35 | **10.17-10.21** (3 runs, 2 boots) |
| decode, tok/s (median of 7) | 231.5 | **250-254** |
| 20K fresh prompt | 13.0 s | **10.3 s** |
| 80K fresh prompt | 18.4 s | **15.4 s** |
| 250K fresh prompt | 50.1 s | **46.7 s** |
| read from the SSD, 80K + 250K prompts | 132.9 GB | 18.6 GB |
| conversation grown to 256K, per turn | 2.7-3.75 s (2026-11-04, ~3.7K new tokens per turn) | **2.0-2.5 s** (~4.5K per turn) |
| swapped out over that conversation | 0 | 0 |
| lowest MemAvailable over that conversation | 2.36 GB (2026-11-04) | 1.68 GB |

The needle came back from every long prompt; the tool-call probe (`tools/tool_probe.py 30`) passed 30 of 30 on
the shipped config (28 of 30 on 2026-11-04, 22 of 30 on IQ3_S the same day). One run per row unless stated;
identical boots differ by about 1.5% per verify window. Where each gain comes from:
[docs/benchmarks.md](docs/benchmarks.md#prompt-slots-in-ram-and-thread-placement-2026-11-10-ud-iq3_xxs).

### Upstream's own benchmark suite (v0.2.1 build, IQ3_S config, 2026-10-23)

`tools/strata_bench.py --long` from Strata v0.2.1 against the running server (the shipped config, thinking off,
temperature 0, 3 runs per test, medians with ranges). Full report:
[docs/strata-bench-2026-10-23](docs/strata-bench-2026-10-23/README.md).

| Test | Prompt tokens | Prompt tok/s | Decode tok/s | First token (s) |
| --- | ---: | --- | --- | --- |
| short chat | 200 | | 186.3 (153.7-254.8) | 0.28 (0.27-0.52) |
| 4K prompt, fresh | 4,024 | 2,446 (1,909-2,830) | | 1.66 (1.44-2.12) |
| 16K prompt, fresh | 16,056 | 3,917 (3,913-4,000) | | 4.12 (4.04-4.12) |
| 32K prompt, fresh | 32,049 | 4,159 (4,150-4,206) | | 7.74 (7.65-7.75) |
| agent session, follow-up turns | up to 14,881 | | 173.5 (145.3-201.5) | 1.31 (0.81-1.79) |

Agent session cache hit 70.0 % (the rest is the new file text of each turn, read once).

### Long prompts on the v0.2.1 build (2026-10-23, fresh boot)

| Prompt | Prompt time | Decode after it | Read from the SSD |
| --- | --- | --- | --- |
| 80K random words | 19.0 s | 153-161 tok/s | 4.7-5.1 GB |
| 149K random words | 31.6-32.6 s | 146-152 tok/s | 8.7-9.0 GB |
| 183K of C++ source | 48.6-49.1 s | 177-186 tok/s | 4.0-4.2 GB |

One thing a fresh boot does not show: an agent conversation that grows past ~160K tokens slows decode on
31 GB of RAM (84 tok/s at 160-200K, 34 tok/s at 200K+ in one long session), and the expert placement it leaves
behind stays slow for short prompts too until a restart (18-22 tok/s, 87% GPU hits; 232-272 tok/s after the
restart). Compact long chats before ~150K. Details: [docs/benchmarks.md](docs/benchmarks.md).

### The v0.1.41 build (history)

#### The shipped config (IQ3_S) and the IQ3_XXS alternative

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

#### Against stock Strata on the same box (IQ3_XXS, 2026-10-07)

| | stock Strata 0.1.33, split 36 | this build, IQ3_XXS |
| --- | --- | --- |
| decode, 600-token answers, greedy | 99-111 tok/s | **188-205 tok/s** |
| 2K fresh prompt | 200-240 tok/s | **597-655 tok/s** |
| 16K fresh prompt | 470-646 tok/s | **2,117-2,315 tok/s** |
| 80K fresh prompt | 886-928 tok/s | **3,146-3,359 tok/s** |
| 2K follow-up on the 80K chat | 7.9 s | **3.8-4.6 s** |
| switching between two chats (30K and 15K) | 20-48 s (full re-read) | **0.3-1.6 s** |
| switching back to a 200K chat from a 5K one | ~47 s (full re-read) | **3.0-3.2 s** (from the SSD) |

#### Tool calls (2026-10-15, IQ3_S)

`tools/tool_probe.py`, 60 two-turn sequences: parallel `read_file` calls with integer arguments, then an
`edit_file` whose strings contain a literal `<parameter=limit>..</parameter>` line, plus a `bash` call.

| template / parser | pass | what failed |
| --- | --- | --- |
| stock Qwen template, stock parser | 21/60 | |
| Sharp template at its medium default | 8/60 | the edit's `new_string` empty in 15 |
| Sharp at xhigh (shipped), stock parser | 30-33/60 | 17 edits cut at the nested `</parameter>`, 14 `bash` calls never written |
| **Sharp at xhigh, our parser fix (old patch 08, now in 01)** | **44/60** | 9 `bash` calls never written, 5 `new_string` never written, 2 turns ended inside the thinking |

Every remaining miss is the model's: the raw engine output shows the call was never written. The model also
writes `<parameter=limit>25</parameter>` and then skips the value's own closer in about half of these edits;
the parser fix reads that correctly, which is the 17 -> 0.

Every run, A/B and rejected knob: [docs/benchmarks.md](docs/benchmarks.md).

## Requirements

- **GPUs:** an RTX 5090 (or another 32 GB Blackwell card) plus a 16 GB NVIDIA card; the second one can sit on a chipset x1 slot.
  The layer split (39) and the VRAM reserves are sized for exactly 32 + 16 GB.
- **RAM:** 32 GB. With the shipped config up, 3 GB stays available at idle and 1.7 GB at the end of a 256K
  conversation, with nothing swapped out. It is sized for a boot at the login screen: started under a desktop
  with a browser open the engine shrinks its RAM copy by itself (11.5 instead of 14.7 GiB here), reads the rest
  from the SSD and decodes about 26% slower per window.
- **Disk:** a fast NVMe with ~140 GB free for UD-IQ3_XXS (55 GB of experts in shards 2-3, the 29 GB shard 4 and
  the 54 GB Q8_0 PLE table); ~135 GB for IQ3_S (55 GB of experts, the 29 GB shard 2 and the 51 GB FP8 PLE
  table) plus 52 GB while `prepare.sh` builds that table (deleted after) and up to 32 GB for conversations
  spilled to disk (`--conversation-spill-mib`, the IQ3_S config only).
- **Software:** Linux, NVIDIA driver, CUDA toolkit (`nvcc`), `cmake`, `ninja`, `git`, `patch`, `curl`, Python 3.10+.

## Install

### 1. Build

```bash
./install.sh
```

- Clones upstream Strata at tag v0.2.1 into `./strata` and applies `patches/` in order
- Builds the engine and the vision helper for sm_89 + sm_120, creates the venv
- Writes `strata/strata-flash-next-ud-iq3xxs-262k.json` (Unsloth UD-IQ3_XXS, the shipped config),
  `strata/strata-flash-next-262k.json` (IQ3_S) and `strata/strata-flash-next-iq3xxs-262k.json`
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
strata/.venv/bin/hf download unsloth/Qwen3.8-Flash-Next-GGUF --include "UD-IQ3_XXS/*" --local-dir models
strata/.venv/bin/hf download ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF --include "mmproj-*" --local-dir models
strata/.venv/bin/hf download alesha-pro/Qwen3.8-Flash-Next-abliterated-GSQ-RCO-Strata-GGUF Huihui-Qwen3.8-Flash-Next-refusal-direction-r.gguf --local-dir models
./prepare.sh
```

- UD-IQ3_XXS is four shards: 1 is the vocabulary (11 MB), 2 and 3 the experts (read in place), 4 Unsloth's
  IQ4_NL PLE table (28.8 GB). The config reads the Q8_0 table instead, but shard 4 must still exist (shard 1
  declares a four-file split). The image encoder weights are ISTA's `mmproj` file (the one tested here)
- `prepare.sh` builds the pack `packs/unsloth-ud-iq3_xxs-v31` with `iq_pack.py --compat-bf16`, downloads
  Unsloth's standalone Q8_0 PLE table (`engram/Qwen3.8-Flash-Next-engram-Q8_0.gguf_file`, 54.4 GB) to
  `models/ple-q8_0.gguf` and patches 82 bytes of its header so v0.2.1 loads it through `--ple-gguf`
  (`tools/ple_header_patch.py`; `--restore` undoes it). Against the BF16 table its relative RMSE is 0.0053; the
  FP8 table's is 0.0265 and IQ4_NL's 0.0757
- Keep `"STRATA_HC_Q8": "0"` in this config: with the Q8 hyper-connection read on, this build garbles tool-call
  arguments on the layer split

For the ISTA quants instead: download `"IQ3_S/*"` (or `"IQ3_XXS/*"`) from the ISTA repository as well and run
`QUANT=IQ3_S ./prepare.sh`; then:

- Shard 1 (55 GB, the experts) is read in place. Shard 2 (28.8 GB) is ISTA's IQ4_NL PLE table; the configs read
  the FP8 table instead, but shard 2 must still exist (shard 1 declares a two-file split). For the IQ3_XXS config
  download `"IQ3_XXS/*"` as well (its shard 2 is the same bytes) and run `QUANT=IQ3_XXS ./prepare.sh`
- The control vector (480 KB) is the refusal direction of huihui-ai's abliterated release, applied at runtime;
  leave the four `--control-vector*` / `--cvec*` arguments out of the config for the stock model
- `prepare.sh` builds the dense pack (`packs/gsq-iq3_s`), the MTP draft runtime (`mtp/rt`) with Strata's own
  tools, and `packs/gsq-iq3_s/tokenizer-sharp`: the pack's tokenizer with the
  [Sharp chat template](https://huggingface.co/peculiar-ragdoll/Qwen-Sharp-Chat-Templates) v22.5.0 (Apache-2.0,
  fetched at a pinned revision and checked) and its default reasoning effort raised from medium to xhigh
- It also builds `models/ple-fp8.gguf`: the PLE n-gram table exactly as Qwen ships it (FP8 E4M3, 51.2 GB), copied
  out of the 33 `Qwen/Qwen3.8-Flash-Next-FP8` shards that hold it (pinned revision) by Strata's own
  `tools/ple_fp8_pack.py`; IQ4_NL is 8% off those values per row. About 3% slower per decode window here.
  `PLE_FP8=0 ./prepare.sh` skips it; then point `--ple-gguf` back at shard 2

### 3. Run

```bash
launchers/flash-next-262k.sh
```

- Serves `http://127.0.0.1:8888/v1`: OpenAI chat completions and Anthropic messages, model name `qwen3.8-flash-next`
- Overrides: `CONFIG=strata-flash-next-262k.json` (IQ3_S) or `strata-flash-next-iq3xxs-262k.json`, `PORT=`, `HOST=`
- Sampling defaults 1.0 / 0.95 / 20, min_p 0, presence_penalty 0 (the model card's thinking set); per-request
  drafter tuning with `"strata_tune": {"spec_min_p": 0.8}`. Keep `presence_penalty: 0.0` in the config: v0.2.1
  merges the model card's sampling per key, which gives thinking-off requests `presence_penalty 1.5`; that
  changes the output and sends every such request down the serial decode loop (16.3-17.3 ms per window instead
  of 12.4-12.9)
- A `max_tokens` that no longer fits the context gets a shorter completion instead of a 400
- Reasoning effort: the template defaults to xhigh; a request's `reasoning_effort` (`none` .. `xhigh`) or
  `chat_template_kwargs.enable_thinking: false` overrides it

> **API key for the network.** Strata v0.2.1 refuses to bind to anything but loopback without an API key.
> For `HOST=0.0.0.0` give the server an API key (the server's `--help` and Strata's docs/DETAILS.md list the ways); clients send it as
> a Bearer token in the `Authorization` header.

## What is in the patch series

Each patch is one tested step, conflict resolutions included; applied to v0.2.1 they rebuild the tested tree
byte for byte (48 files, `patches/MANIFEST.sha256`).

| # | Source | What it does |
| --- | --- | --- |
| 01 | ours + carried PRs | the whole v0.1.41 series (13 patches, see [the previous README](https://github.com/ExTV/strata-5090-4070/blob/1fa7992/README.md#what-is-in-the-patch-series)) merged onto v0.2.1 (1,770 upstream commits), 20 files / ~100 hunks resolved by hand. Upstream already had and kept: merge-v2 attention, the PromptEncoder (#567), the tail skip, the park gain (#2265), #1599, the commit batch, the lend-ring fix, the grouped resident gathers, RAM adapt (ours is gated to splits with no stages), the drafter's `mtp_first`. Ours on top: `--prefill-main` with the chained split-wise reads, the SSD spill, the prefix store under `--prefill-main`, `pread` expert copies, the PLE ticket / prefetch / early chain, slot expiry, the nested-parameter parser fix, `--kv-resident-later`, the draft K/V copy at load |
| 02 | PR #3404 | a parked conversation's older copies are dropped when a newer one supersedes them, so the parking budget is not spent on dead snapshots |
| 03 | upstream 70f42407 (#3441, #3075) | a tool call counts only when it names a declared tool (anything else goes back as text, so a client never runs a tool it did not offer); an envelope that drifted by a token (`<=NAME>`, `<function:NAME>`, `<NAME>`) is read as the call when NAME is declared; unread `<tool_call>` blocks are counted in the server window |
| 04 | ours | the SSD spill: a request that picked another conversation's spill to restore no longer lets the outgoing conversation's park delete that file first (conversations that share a system prompt and tools match each other's checkpoints; with `--short-read 128` the tool probe crashed the engine 3 times on `spill-N.ses: No such file`, 0 after the fix in 114 spill reads); new `--no-conversation-spill-idle` writes a spill only when another conversation comes in, not ahead of it while idle (the switch pays the write, 0.2-0.7 s) |
| 05 | ours | under `--prefill-main` prompt parts with pictures chain split-wise like text (the picture rows replace the token embedding at layer 0 on the 5090, every stage holds the image positions); before, every image part ran whole-model on the 5090 and streamed the 4070's 9.6 GiB of experts from the SSD: OCR crop (1,199 tokens) 5.13 s / 10.75 GB -> 1.23 s / 0.32 GB, full page 3.02 s / 10.35 GB -> 1.31 s / 0.04 GB, an image inside a 34K conversation 2.88 s / 7.24 GB -> 1.65 s / 0.01 GB; OCR answers identical |
| 06 | upstream #3470, #3350, #3602 | three upstream fixes that came after v0.2.1: copy streams and events of short-lived threads go back to a pool instead of leaking a few MiB of VRAM on the later card per long cold prompt (#3470); a conversation checkpoint whose copy ran out of memory is skipped instead of ending the request (#3350, upstream f62589fd); a PLE read that failed no longer leaves the next ticket waiting for ever (#3602, upstream ebe3383a) |
| 07 | PR #4844 | with `--pipeline-windows 2` and `--adapt-async 1` on a layer split, an adaptive round finished after the pipelined loop marked a stale range, so newly placed experts ended up in neither VRAM nor RAM and were read from the file: decode drifted down over hours until a restart. Two lines; in upstream since v0.2.12 |
| 08 | PR #5108 | the MMQ row table gets room for ggml's stream-k fixup read, which ran past its end on long prompts on the second card of a layer split (`prefill copy_i32: illegal memory access`). In upstream since v0.2.12 |

Measured and left out on v0.2.1: the PR #3453-style sm_89 MMVQ table re-tuned on the 4070 Ti SUPER (bitwise
parity on both cards, decode neutral: the 4070 holds 9 of 48 layers); `STRATA_UNBUFFERED_LOAD=1` with an explicit
`--resident-budget-gib 17.5` (O_DIRECT file tier, equal on fresh boots). Details for every piece:
[docs/how-it-works.md](docs/how-it-works.md).

## Tuning in the shipped config

The UD-IQ3_XXS config differs from the IQ3_S one (the table below) in these settings:

| Setting | Why |
| --- | --- |
| `--prefill 4096` with `--resident-budget-gib 14.7` | the prompt path borrows expert-cache slots from the 5090 and gives them back after the prompt; a borrowed slot whose expert has no RAM copy is streamed from the SSD on every chunk. At chunk 8192 it borrows 1,543 slots and 13.2 GiB held 193 of them; at 4096 it borrows 962 and 14.7 GiB holds them all (12.83 GiB of experts outside VRAM + 1.87 GiB for the loan). Either change alone is a few percent; together 80K 18.4 -> 15.4 s and SSD reads -85%. `--prefill auto:4096` is not the same thing: `auto` never picks below 8192 |
| `--aux-cpus auto --host-core sibling` | on a hybrid CPU (8P+12E here) the engine takes 13 pool workers, which leaves CPUs free: its 72 helper threads (the CUDA driver's, the adaptive tier's, the prompt helpers) move to those, and the host thread to the first core's SMT sibling. Threads only, never a result: 11.0-11.1 -> 10.5-10.6 ms per window with `--aux-cpus auto`, 10.2 with both |
| `--conversation-cache-mib 0`, no spill or prefix directory | parking, the SSD spill and the prefix store are off: on 31 GB they cost RAM the 256K conversation needs, and a same-chat follow-up is reused from the live state anyway. Switching chats re-reads the other one |
| `--ple-gguf .../ple-q8_0.gguf` | Unsloth's Q8_0 PLE table, five times closer to BF16 than the FP8 one |
| `"STRATA_HC_Q8": "0"` | see step 2 |
| `STRATA_GR_NORM_FAST`, `SCORES_HALVE`, `TOPK_SPLIT`, `QIL`, `SIDE_MIXER=2`, `ATTN_DAILY`, `GU_SWIGLU`, `GR_UP75`, `GR_DOWN_TG`, `FUSE_HEAD_GR`, `LFUSE`, `GR_V3`, `IO_THREADS=64`, `UNBUFFERED_LOAD` | upstream's opt-in kernels and readers that measured faster here (on IQ3_S, 2026-10-23): decode about -4.5% per window, 80K prompts -9%. All bitwise except `GR_V3` (the hyper-connection read in another FP32 summation order) |

Measured and not kept on this config: `--prefill 2048` (80K 17.0 s), `--pool-affinity p-cores` (neutral),
RAM budget 14.4 at chunk 8192 (covers 823 of 1,549 borrowed slots; 80K 17.3 s and 1.3 GB less RAM margin).

| Setting | Why |
| --- | --- |
| `"layer_split": "39"` | layers 0-38 on the 5090, 39-47 + drafter on the 4070, which holds every expert of its layers. 39 since 2026-10-15 evening, together with the resident K/V below (alone it equals 38); 37 -> 38 earlier that day was -2% per verify window |
| `--kv-resident-later 0` | ours (in patch 01): the 4070 keeps the whole K/V of its attention layers in VRAM (+0.7 GB there, 0.8 GB of pinned RAM back): decode after 81-203K prompts +6-9%, 203K prefill 61.9 -> 57.2 s, 81K 24.5-29 -> 23-24 s; short prompts +0.2 ms per window (1.5-2.5%) |
| `"vision": {"cuda_device": 1}` | the image encoder runs on the 4070 (1.28 GB there, 1.7 GB on the 5090), which is what makes room for the split |
| `--prefill auto:16384` | IQ3_S has 3,000 fewer GPU-resident experts than IQ3_XXS; with 16K chunks every lent slot stays in locked RAM (32K: 41% of a chunk's loan re-read from the file); speed a wash, RAM cleaner. The IQ3_XXS config keeps 32768 |
| `STRATA_PM_MTP_BATCH=1` | ours (in patch 01): the draft layer's prompt K/V on the 5090 (long prompts -20..25% TTFT) |
| `--mtp-hnorm stream` | upstream's opt-in drafter norm (one RMS per hyper-connection stream instead of one over all four); on since 2026-10-13 together with the park gain, not A/B'd on its own |
| `--conversation-cache-park-gain 4096` | park again only after 4,096 new tokens: no snapshot churn on a long single conversation |
| `--control-vector-scaled FILE:1.0 --control-vector-layer-range 4 44 --cvec-mode project --cvec-dir per-layer` | the refusal direction projected out of the residual stream at runtime; speed-neutral, the weights are ISTA's own; `"experimental_speed_projection": false` in a request turns it off |
| `"tokenizer": ".../tokenizer-sharp"` | the Sharp template at xhigh: tool probe 33/60 vs 21/60 stock, short answers in a third of the tokens; at its medium default it dropped to 8/60, so effort is what matters |
| `--short-read 128` | new text up to 128 tokens goes through the decode windows; longer parts chain split-wise (~0.35 s + 0.4 ms per token against 2.4-4 ms per token in the windows): follow-ups of 285 / 425 / 700 tokens 0.8-1.1 / 1.3-1.8 / 2.1-3.0 s at 768 -> 0.40 / 0.47 / 0.63-0.68 s |
| `--conversation-cache-mib 1024`, 8 slots | parked chats survive the small side requests chat apps send; kept small so the engine has RAM |
| `--conversation-spill-dir conversation-spill` | a chat too big to park is written to the SSD (~16 KB per token) and read back from there |
| `--no-conversation-spill-idle`, `--conversation-cache-min-tokens 1024` | fewer SSD writes: one day's log showed 231 GB of spill writes, 114 GB of them speculative idle spills and 32 GB from chats under 1K tokens (every spill is at least ~230 MB: the recurrent state is a fixed size). Short chats are neither parked nor spilled; a long one is written when another conversation comes in |
| `STRATA_RAM_ADAPT=256`, `"expert_profile_save"` | the RAM copy takes in the hot experts the traffic reads from the file, between requests (placement only, the math is the same); the learned placement is saved every 10 min and at exit and the next boot starts from it. Before, long agent days drifted onto the 9.6 GiB of file-only experts: decode 200 -> 35-50 tok/s over 18 h, 5-14 GB of file reads per request |
| `--conversation-cache-min-free-mib 1024` | the default floor (2,560) refuses every park at headroom 4 |
| `--prefix-cache-dir prefix-cache` | a known system prompt is restored from disk (about 430 MB per 20K tokens) |
| `STRATA_RESIDENT_HEADROOM_GIB=4` | the RAM the lend region leaves free: every borrowed slot stays in locked RAM, so refilling them after a prompt takes 0.15 s instead of 6 s |
| `STRATA_PF_FUSED=1` | fused int8 tensor-core prompt kernels for the IQ packs (+9-13% on prompts) |
| `MALLOC_MMAP_THRESHOLD_`, `MALLOC_ARENA_MAX` | about 0.7 GB more available RAM, speed-neutral |
| `--kv int8` | the KV cache stays at 8 bits |

`STRATA_ROUTE_TAIL_SKIP` is on by default upstream since v0.1.42 and the shipped
configs turn it off (`"STRATA_ROUTE_TAIL_SKIP": "0"`): it changes answers (upstream measured KL 0.003-0.006) for
about 3% of a decode window on IQ3_S. The v0.2.1 numbers above were measured with it off; the v0.1.41 history
tables with it on.

Headroom 4 assumes nothing else runs on the box: about 3.5 GB of engine memory goes to zram, and now and then
a tool step stalls for a couple of seconds on page faults. Use 14 if you work on the desktop while it serves
(prompts ~40% slower, refills 6 s). Booting with a browser open cut the RAM expert tier from 16.4 to 5.2 GiB
once and decode to a third: the tier is sized at boot.

Parking 1024 MiB holds chats up to about 50K tokens. Anything longer is written to the spill directory
when another conversation comes in (a 200K chat is a 3.1 GB file; the switch pays the write, 0.2-0.7 s for the
usual sizes), and the file is kept after it is read back, so the next switch reuses it while the chat is at most
8,192 tokens past it. Chats under 1,024 tokens are neither parked nor spilled. The files belong to one server
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
| `tools/agent_steps.py TAG [SEED]` | a 13K first message and four tool-result follow-ups (1.5K / 2.4K / 5.4K / 0.5K tokens): prompt seconds and SSD GB per step (the chained-read gate; `NVME=` names the device) |
| `strata/tools/strata_bench.py --url http://127.0.0.1:8888 --long` | upstream's own suite (short chat, 4K / 16K / 32K prompts, a 5-turn agent session): the report in `docs/strata-bench-2026-10-23/` |
| `tools/snapshot.py` | page faults, swap, direct reclaim, NVMe, GPU counters; diff them around a run |
| `tools/prompt_bench.py WORDS...` | fresh random-word prompts with a needle and a follow-up (`23700 74000` = 80K and 250K tokens) |
| `tools/grow_chat.py [LIMIT]` | one conversation grown to the context limit, ~4.5K tokens of source per turn: seconds per turn, decode, MemAvailable |
| `tools/ple_header_patch.py FILE` | makes Unsloth's standalone PLE table loadable through `--ple-gguf` (run by `prepare.sh`) |

## Status

- The patch series is checked in CI against a pristine v0.2.1 checkout.
- The UD-IQ3_XXS config is what runs here every day (since 2026-11-04; these settings since 2026-11-10). The
  IQ3_S config ran here until then; the ISTA IQ3_XXS config was carried forward and has not been booted on the
  v0.2.1 build.
- `install.sh` and `prepare.sh` have not been run end to end from a clean checkout yet, and the UD-IQ3_XXS
  steps of `prepare.sh` (the pack, the Q8_0 table download) were done by hand here, not through the script;
  the header patch tool was checked against the real file. Reports welcome.
- Upstream is at v0.2.13. This build stays on v0.2.1 on purpose: layer splits like this one report slower
  prompts and decode on the newer engines, and the two fixes that mattered here (patches 07 and 08) are carried.

## License

MIT ([LICENSE](LICENSE)). Strata is MIT ([LICENSE.strata](LICENSE.strata)). The Sharp chat template that
`prepare.sh` downloads is Apache-2.0 (peculiar-ragdoll); the control vector is from alesha-pro's release.
