# Tuning in the shipped configs

## UD-IQ3_XXS (the default)

It differs from the IQ3_S config (the second table) in these settings:

| Setting | Why |
| --- | --- |
| `--prefill 4096` with `--resident-budget-gib 14.7` | the prompt path borrows expert-cache slots from the 5090 and gives them back after the prompt; a borrowed slot whose expert has no RAM copy is streamed from the SSD on every chunk. At chunk 8192 it borrows 1,543 slots and 13.2 GiB held 193 of them; at 4096 it borrows 962 and 14.7 GiB holds them all (12.83 GiB of experts outside VRAM + 1.87 GiB for the loan). Either change alone is a few percent; together 80K 18.4 -> 15.4 s and SSD reads -85%. `--prefill auto:4096` is not the same thing: `auto` never picks below 8192 |
| `--aux-cpus auto --host-core sibling` | on a hybrid CPU (8P+12E here) the engine takes 13 pool workers, which leaves CPUs free: its 72 helper threads (the CUDA driver's, the adaptive tier's, the prompt helpers) move to those, and the host thread to the first core's SMT sibling. Threads only, never a result: 11.0-11.1 -> 10.5-10.6 ms per window with `--aux-cpus auto`, 10.2 with both |
| `--conversation-cache-mib 0`, no spill or prefix directory | parking, the SSD spill and the prefix store are off: on 31 GB they cost RAM the 256K conversation needs, and a same-chat follow-up is reused from the live state anyway. Switching chats re-reads the other one |
| `--ple-gguf .../ple-q8_0.gguf` | Unsloth's Q8_0 PLE table, five times closer to BF16 than the FP8 one |
| `"STRATA_HC_Q8": "0"` | with the Q8 hyper-connection read on, this build garbles tool-call arguments on the layer split |
| `STRATA_GR_NORM_FAST`, `SCORES_HALVE`, `TOPK_SPLIT`, `QIL`, `SIDE_MIXER=2`, `ATTN_DAILY`, `GU_SWIGLU`, `GR_UP75`, `GR_DOWN_TG`, `FUSE_HEAD_GR`, `LFUSE`, `GR_V3`, `IO_THREADS=64`, `UNBUFFERED_LOAD` | upstream's opt-in kernels and readers that measured faster here (on IQ3_S, 2026-10-23): decode about -4.5% per window, 80K prompts -9%. All bitwise except `GR_V3` (the hyper-connection read in another FP32 summation order) |

Measured and not kept on this config: `--prefill 2048` (80K 17.0 s), `--pool-affinity p-cores` (neutral),
RAM budget 14.4 at chunk 8192 (covers 823 of 1,549 borrowed slots; 80K 17.3 s and 1.3 GB less RAM margin).

## IQ3_S (and what both configs share)

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
