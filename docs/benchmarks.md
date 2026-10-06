# Benchmarks

All on 2026-10-02 to 2026-10-06, RTX 5090 + RTX 4070 Ti SUPER (x1), 31 GB RAM, Arch Linux, ISTA GSQ-RCO
IQ3_XXS, 262,144 context, layer split 36, int8 KV with 32,768 resident cells, vision on. The Strata base
moves through the sections: 0.1.33, 0.1.37, 0.1.38 with six PRs, the Strata-DualGPU fork, then the fork's later commits with the
lend region in RAM, then upstream 0.1.39 with the fork's work as PRs, then the 2026-10-06 PR updates with headroom 4 (the shipped config, last section).
`tools/bench.py`: five 600-token greedy answers with thinking off (decode median), fresh prompts of
~2K (twice), ~16K and ~80K tokens of random words (prefill tok/s), then a 2K follow-up on the 80K
conversation; `tools/decode_after.py`: five more answers right after the 80K prompt. "faults" is
the major-page-fault delta over the bench (`tools/snapshot.py`), the measure of the RAM-pressure
state that boot was in; compare rows with similar fault counts.

## Stock 0.1.33, split sweep (no patches)

| split | decode median | 16K | 80K | 80K follow-up |
| --- | --- | --- | --- | --- |
| 36 | 109 (second run 99) | 470 | 886 | 7.9 s |
| 37 | 106 / 70 | 556 / 694 | 989 / 1,017 | 6.9 s |
| 38 | 70 / 86 | 760 / 740 | 1,182 / 1,179 | 5.9 s |
| 39 | 92 | 499 | 1,127 | 5.9 s |
| 36, `--prefill 1024` | 107 | 273 | 265 | 7.2 s |
| 36, Strata 0.1.31 vs 0.1.33 same day | 99 / 111 | 639 / 646 | 922 / 928 | |

The README's "stock" ranges (decode 99-111, 16K 470-646, 80K 886-928) are the spread of the split-36
rows above. Until this commit the bench seeded its prompts from Python's per-process string hash,
so prompts differed between runs; they are random words of the same shape, so the numbers stand,
but runs are only identical from this commit on.

## `--prefill-main` vs stock, same day, fresh boots

| | decode median | 2K | 16K | 80K | follow-up | decode after 80K |
| --- | --- | --- | --- | --- | --- | --- |
| stock split 36 | 79 | 243 | 637 | 896 | 7.8 s | 136 |
| prefill-main (first port) | 98 | 330 | 694 | **1,791** | 6.1 s | 84 |

## Final 0.1.33 build (PR #385, the 0.1.35 hunks and the prefill-main port, "v4") and its A/Bs, same evening

| boot | decode median | 2K | 16K | 80K | follow-up | decode after 80K | faults |
| --- | --- | --- | --- | --- | --- | --- | --- |
| previous build, whole-window copies (control, run 1) | 82 | 222 | 614 | 638 | 16.0 s | 76 | 16.4 M |
| previous build (control, run 2) | 93 | 248 | 673 | 658 | 19.3 s | 68 | |
| **v4** | 101 | 302 | 635 | 696 | 13.8 s | 82 | 11.3 M |
| v4, parking off | 107 | 220 | 940 | **1,250** | 8.0 s | 89 | 6.3 M |
| v4, `--prefill auto:16384` | 76 | 307 | 922 | 1,159 | 9.6 s | 106 | 1.0 M |
| v4, parking 2 GB / 2 slots | 76 | 300 | 630 | 788 | 18.6 s | 80 | 10.1 M |
| v4, `STRATA_PM_SHARE=1` (v3 binary) | 59 | 196 | 712 | 740 | 20.3 s | **28** | 8.5 M |
| v4 production boot, spec-min-p 0.7, swappiness 10 | 99 | 251 | 718 | 663 | 14.5 s | 72 | 14.0 M |

## Prompt chunk size under `--prefill-main` (v4, spec-min-p 0.8, one boot each, same hour)

| `--prefill` | decode median | 2K | 16K | 80K | follow-up | decode after 80K | faults | NVMe read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| auto (8192) | 94 | 182-209 | 459 | 510 | 12.9 s | 64 | 24.0 M | 207 GB |
| auto:16384 | 84 | 216-237 | 698 | 1,337 | 12.2 s | 106 | 1.35 M | 340 GB |
| **auto:32768** | 91 | 146-200 | **800** | **1,451** | 12.4 s | **108** | 1.14 M | 317 GB |

Every chunk re-streams the experts of every layer, so fewer chunks per prompt means fewer
synchronous faults; the bytes read barely change (the readahead hint brings whole blobs in
either way), the faults do. The two earlier 16384 boots (`v4-pf16k`, 1,159 tok/s at 1.0 M faults)
agree. The decode medians are temperature-0 numbers and within the usual boot-to-boot band.

## `pread` expert copies (now patch 11), chunk 32768, back to back

| | decode median | 2K | 16K | 80K | follow-up | decode after 80K | faults | swap-in | NVMe read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| memcpy from the mmap (control) | 95 | 138 / 238 | 734 | 1,471 | 10.4 s | 107 | 951 K | 3.2 GB | 325 GB |
| **`STRATA_BLOB_PREAD=1`** | 108 | **348 / 376** | **985** | **1,796** | **6.1 s** | 106 | **13.8 K** | 47 MB | 202 GB |

Decode numbers at temperature 0 (the bench) are below the sampled ones: real use at 0.6 / 0.95 / 20
with spec-min-p 0.7-0.8 measured 128-134 tok/s median on the same prompts (`tools/spec_min_p_sweep.py`).

## Correctness (v4)

- 40K prompt with two needles, then four follow-ups and a 20K extension with a third needle: every
  answer right (`tools/needle_followups.py`); follow-ups 0.7-1.2 s, the extension 51.7 s.
- Two alternating conversations (30K and 15K), four rounds including "plus one" and "spell it
  backwards": 8/8 right, switches 0.6-1.2 s (`tools/parking_check.py`).
- Strata's own `kv_stream_parity` (streamed vs resident KV, bitwise, int8/fp16/q4_0) passes on the
  patched tree.

## spec-min-p (per request, no restart, temperature 0.6, seed 11, 600 tokens, 5 prompts)

| threshold | 0.3 | 0.5 | 0.7 | 0.8 | 0.9 |
| --- | --- | --- | --- | --- | --- |
| sweep 1, median tok/s | 78 | 114 | 128 | | |
| sweep 2, median tok/s | | | 97 | 134 | 121 |

## Upstream 0.1.37 base and `STRATA_PF_FUSED=1` (2026-10-03, the shipped config)

The v4 patch set (then three patches) on v0.1.37, pread on, chunk 32768, spec-min-p 0.8; MMQ and the fused kernels
alternated, two rounds each, one boot per row. The MMQ rows reproduce the 0.1.33 v5 numbers above.

| | decode median | 2K | 16K | 80K | follow-up | decode after 80K |
| --- | --- | --- | --- | --- | --- | --- |
| MMQ, round 1 | 108 | 339 / 341 | 1,080 | 1,826 | 6.7 s | 114 |
| MMQ, round 2 | 108 | 336 / 347 | 1,086 | 1,827 | 6.7 s | 115 |
| **fused, round 1** | 110 | 355 / 356 | 1,212 | 1,969 | 5.9 s | 115 |
| **fused, round 2** | 106 | 360 / 372 | **1,240** | **1,994** | **5.8 s** | 118 |

Major faults per bench stayed in the 1-2 K range on every row. Correctness on the fused build: the
40K needle with four follow-ups and the 20K extension 5/5 (follow-ups 0.4-0.7 s, the extension 15.8 s),
the two alternating conversations 8/8 with 0.6-0.7 s switches.

## Upstream 0.1.38 plus PRs #603, #547, #567, #510, #572, #525 (2026-10-03 afternoon)

Same config as the 0.1.37 rows (fused kernels, pread, chunk 32768, spec-min-p 0.8, parking 6 GB).

| | decode median | 2K | 16K | 80K | follow-up | decode after 80K |
| --- | --- | --- | --- | --- | --- | --- |
| 0.1.37 fused (above, same day) | 106-110 | 355-372 | 1,212-1,240 | 1,969-1,994 | 5.8 s | 115-118 |
| **0.1.38 + the six PRs** | 110 | 373 / 376 | 1,305 | 2,094 | 5.5 s | 117 |

Needle 5/5 (follow-ups 0.4-0.5 s, the 20K extension 15.4 s), parking 8/8 (switches 0.5-0.7 s). The
prompt path's loan fell from 6,939 to 6,243 slots (#547).

## Layer split 38 and the stock split prefill (2026-10-03 morning, 0.1.37 build)

| arm | decode | 2K | 16K | 80K | follow-up | decode after 80K |
| --- | --- | --- | --- | --- | --- | --- |
| split 38, `--prefill-main` (the 4070 holds all 5,120 pairs of its 10 layers) | 104 | 336 / 348 | 1,223 | 2,018 | 6.0 s | 108 |
| split 38, stock split prefill, parking off | 106 | 285 / 294 | 618 | 1,203 | 7.5 s | 114 |
| the same with `--ple-inflight 256` | 109 | 282 / 293 | 618 | 1,206 | 7.5 s | 117 |

The 80K prompt read 99-111 GB from NVMe in every arm: the lent experts, not the miss rate, are the
traffic (docs/how-it-works.md, "What the prompt loan costs").

## Parking off versus on (2026-10-03 evening, 0.1.38 build, alternated)

The bench's requests are separate conversations, so with parking on each request parks the previous
one (50-500 ms, inside the measured time). The last two rows also had a 112K-token session parked
first.

| state | decode | 2K | 16K | 80K | follow-up | decode after 80K | NVMe read per bench |
| --- | --- | --- | --- | --- | --- | --- | --- |
| parking off, round 1 | 112 | 375 / 378 | 1,306 | 2,127 | 5.5 s | 126 | 158 GB |
| parking off, round 2 | 112 | 390 / 388 | 1,324 | 2,129 | 5.6 s | 124 | 156 GB |
| parking 6 GB, round 1 | 106 | 364 / 373 | 1,273 | 2,090 | 5.5 s | 115 | 163 GB |
| parking 6 GB, round 2 | 111 | 376 / 381 | 1,282 | 2,093 | 5.4 s | 113 | 163 GB |
| 6 GB plus a 112K session parked, round 1 | 99 | 384 / 385 | 1,335 | 2,086 | 5.4 s | 113 | 173 GB |
| 6 GB plus a 112K session parked, round 2 | 99 | 388 / 388 | 1,312 | 2,181 | 5.5 s | 114 | 173 GB |

Freeing the parking RAM buys about 2% on fresh prompts and nothing on follow-ups. Parking stays. The
four-slot limit evicted the 112K snapshot after four short conversations, so `--conversation-cache-slots`
matters as much as the byte budget when several clients talk to the server.

## The Strata-DualGPU fork (2026-10-03 evening)

Fork commit of 2026-10-03 plus the same PRs and patches; `--resident-experts` (6.92 GiB page-locked
RAM copy of the experts neither card holds), `--vram-reserve-later-mib 700`, `--pipeline-windows` at its
default of 2, parking 4 GB; everything else as above.

| | decode median | 2K | 16K | 80K | follow-up | decode after 80K |
| --- | --- | --- | --- | --- | --- | --- |
| 0.1.38 + PRs (above, same day) | 110 | 373 / 376 | 1,305 | 2,094 | 5.5 s | 117 |
| **the fork + PRs + patches** | **170** (136-190) | **449 / 460** | 1,359 | 2,121 | **4.4 s** | **155** |
| the same with `--pool-workers 13` | 167 | 439 / 445 | 1,356 | 2,098 | 4.5 s | 164 |

Correctness on the fork: needle 5/5 (follow-ups 0.3-0.4 s, the extension 14.3 s), parking 8/8
(switches 0.4-0.5 s, restores 40-80 ms), a second set of five decodes after everything else at 172
median, planets / iterative Fibonacci / the 9:40 train (14:05) right, no refill failures or rollback
errors in the log, decode expert hits 99.2% with the misses served from the RAM copy. The prompt path
still read 293 GB from the GGUF over the whole test: the loan is untouched by the fork. With
`--vram-reserve-later-mib 300` the boot failed ("mtp: the draft head does not fit", 178 MiB needed,
155 free on the 4070).

RAM with the model up: 23.4 GB used, 8.3 GB available. The 5090 idles at 32,071 MiB of 32,607 (the
pipeline's GDN snapshot and second verifiers took the last 500 MiB); the 4070 at 15,800.

## The fork's later commits: per-card weights (2026-10-04)

Fork head of 2026-10-03 21:38 UTC with the same PRs and patches; the 5090 keeps all 48 layers' dense
weights for `--prefill-main` (now patch 10), the 4070 its own 12. Same config otherwise.

| | 4070 holds | experts in RAM | decode median | 2K | 16K | 80K | follow-up | decode after 80K |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fork of the evening before (above) | about 5,200 of 6,144 | 6.56 GiB | 170 | 449 / 460 | 1,359 | 2,121 | 4.4 s | 155 |
| **later commits, split 36** (two runs) | 6,144 of 6,144 | 4.83 GiB | 173, 174 | 431-450 | 1,266-1,269 | 2,104-2,160 | 4.7-4.9 s | 175, 161 |
| split 35 | 6,292 of 6,656 | 4.46 GiB | 161 | 393 / 419 | 1,300 | 2,103 | 5.1 s | 163 |
| split 34, later-card reserve 512 | 6,262 of 7,168 | 4.36 GiB | 168 | 397 / 406 | 1,285 | 2,111 | 5.1 s | 161 |

RAM 20.2 GB used, 11.6 available (23.4 / 8.3 before); VRAM 32,007 / 14,941 MiB. Needle 5/5 and
parking 6/6 on every row.

## The lend region in locked RAM (now patch 12, 2026-10-04, same build, one session)

`step` columns: `tools/step_times.py` on real web text, a 12.7K-token first message, then three reads
each of 1.3K, 3.1K and 5.6K tokens (medians).

| | locked | decode / after 80K | 2K | 16K | 80K | follow-up | first 12.7K | steps 1.3K / 3.1K / 5.6K | lowest available RAM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| control (no lend region) | 4.83 GiB | 170 / 179 | 420 / 419 | 1,282 | 2,127 | 4.8 s | 10.0 s | 4.65 / 4.99 / 6.26 s | about 5 GB |
| headroom 4 (all of it), parking 2 GB | 14.59 | 174 / 178 | 566 / 590 | 2,175 | 3,089 | 3.6 s | 5.4 s | 3.32 / 3.47 / 4.18 s | 0.85 GB |
| the same, parking 4 GB, a 112K chat sent first | 14.59 | 173 / 173 | 598 / 577 | 2,177 | 3,173 | 3.6 s | 5.5 s | 3.50 / 3.78 / 4.46 s | 1.1 GB |
| headroom 7, parking 4 GB | 13.02 | 176 / 169 | 585 / 588 | 2,212 | 2,491 | 3.6 s | 5.6 s | 3.37 / 4.06 / 4.77 s | 2.1 GB |
| **headroom 10, parking 4 GB, a 112K chat parked first (shipped until 2026-10-05)** | 10.01 | 179 / 171 | 563 / 578 | 2,165 | 2,130 | 3.7 s | 5.6 s | 3.33 / 3.56 / 4.16 s | 2.3 GB |

Parking check (two conversations of 30K and 15K alternating): 0.4-0.5 s per switch on the control and
the shipped row; with everything locked every park was refused by the RAM admission floor and the
switches took 5.4-8.1 s, answers still right. On the shipped row the 112K conversation parked (2.3 GB),
seven later parks were refused while the 80K bench held the RAM, and parking resumed after it. Needle
5/5 on every row. Swap in use grew from 1.9 to 6.6 GB with everything locked, 1.9 to 4.2 GB on the
shipped row.

## `--short-read` (2026-10-04, one boot, per-request threshold, real web text on a 12.7K-74K conversation)

Seconds for a follow-up message of that many new tokens, two passes:

| new tokens | 64 (default) | 256 | 512 | 1024 |
| --- | --- | --- | --- | --- |
| 69 | 0.33 | 0.31 | 0.34 | 0.32 |
| 130 / 161 | 1.66 / 1.70 | 0.47 / 0.46 | 0.46 / 0.42 | 0.43 / 0.47 |
| 251 / 283 | 1.72 / 2.15 | 0.53 / 1.98 | 0.65 / 0.84 | 0.66 / 0.72 |
| 327 / 401 | 2.14 / 2.07 | 2.26 / 2.06 | 2.40 / 1.01 | 0.84 / 0.98 |
| 637 / 683 | 2.00 / 2.64 | 2.03 / 2.39 | 2.16 / 2.29 | 1.47 / 1.38 |
| 741 | 2.24 | 2.38 | 2.51 | 1.64 |
| 884 | 2.85 | 2.81 | 2.84 | 3.41 |
| 1,111 | 2.80 | 2.45 | 2.56 | 3.32 |
| 1,511 / 1,572 | 3.66 / 3.67 | 3.76 / 3.57 | 3.71 / 3.55 | 3.81 / 3.43 |
| 2,141 / 3,039 | 4.23 / 4.12 | 4.03 / 4.36 | 4.22 / 4.31 | 3.94 / 4.07 |

A message part counts a few tokens more than the new text (the turn's header), so a size just under a
threshold can fall on either side. Shipped: 768. This was measured before patch 09; with it the
batched path's fixed cost is lower and the break-even may sit lower too (not re-measured).

## A client that merges a turn's tool calls (now patch 13, 2026-10-04)

`tools/merged_tool_turn.py`, four tool steps of about 3K tokens each, tokens reused of the prompt:

| | step 2 | step 3 | step 4 | the next user turn |
| --- | --- | --- | --- | --- |
| ids without a response marker (`OLD_IDS=1`) | 300 of 6,472 | 300 of 9,474 | 300 of 12,641 | |
| patch 13 | 3,396 of 6,484 | 6,510 of 9,498 | 9,524 of 12,677 | 12,670 of 12,750 |

In real use before the patch, one 30-call turn re-read 24K to 134K tokens on each of 19 requests
(15-51 s per step); after it, 33 requests over three conversations each reused the whole live
session. The server suite passes with the patch (180 tests, 10 of them new).

## Upstream 0.1.39 with Hardin22's PRs (2026-10-05)

v0.1.39 plus #848 #859 #851 #863 #876 #904 #905 #910 (the fork's work, sent upstream), the five open PRs
and our patches 10-13; the config adds `--trim-stage-weights --pipeline-windows 2 --adapt-async 1`
(fork defaults, opt-in upstream), the PLE prefetch flags, `"format_fixes": "stranded-call"`, headroom 14
and parking 6 GB / 8 slots. Measured with the abliterated build of the same GGUF
(`Qwen3.8-Flash-Next-GSQ-RCO-abliterated-IQ3_XXS`, same quant format and tensor types as the ISTA file).
`tools/bench.py` plus `tools/step_times.py` on real text (steps of 1.5K / 2.7K / 5.9K tokens), each
row pooled over repeated boots:

| | decode median | 2K | 16K | 80K | steps 1.5K / 2.7K / 5.9K |
| --- | --- | --- | --- | --- | --- |
| base + malloc env | **193.5** | 496 | 1,350 | 2,168 | 3.79 / 4.29 / 5.81 s |
| **`STRATA_SPLIT_SMALL_OWN=3072` + malloc env (shipped)** | 176 | **572** | **1,434** | **2,256** | **3.35 / 3.60 / 5.02 s** |
| `STRATA_SPLIT_SMALL_OWN=2048` | ties 3072 | | | | |
| `STRATA_SPLIT_SMALL_OWN=4096` | 167 | | | | no gain over 3072 |
| `STRATA_PM_SHARE=1` | 78 | | | | |
| `STRATA_MTP_KV=f16`, `STRATA_PREFILL_LEND_PCT=60`, `STRATA_PREFILL_HELP=1` | neutral | | | | neutral |

The malloc env (`MALLOC_MMAP_THRESHOLD_=1048576 MALLOC_ARENA_MAX=4`) gives about 0.7 GB more available
RAM and is speed-neutral. `--kv q4_0` was not run: the KV stays at 8 bits.

Correctness on the shipped config: the 40K needle with four follow-ups and the 20K extension all right,
parking 8/8 (restores 0.4-0.5 s), the merged tool turn reuses the live session on every step, no park
refused during the run.

### Depth table

`tools/depth_bench.py`: at each depth a fresh prompt of real text (Strata's own docs and source, sized
with the server's token counter, a unique first line so nothing comes from cache), then a 256-token
answer, streamed, greedy, thinking off. Prefill = prompt tokens / time to first token, decode = answer
tokens / the rest.

| depth | prefill | decode |
| --- | --- | --- |
| 2K | 579 tok/s | 154 tok/s |
| 32K | 1,742 tok/s | 146 tok/s |
| 62K | 2,503 tok/s | 138 tok/s |
| 92K | 2,727 tok/s | 145 tok/s |
| 122K | 2,792 tok/s | 141 tok/s |
| 152K | 2,727 tok/s | 129 tok/s |
| 182K | 3,116 tok/s | 130 tok/s |
| 212K | 3,131 tok/s | 129 tok/s |
| 242K | 3,169 tok/s | 121 tok/s |
| 260K | 3,269 tok/s | 136 tok/s |

The 260K prompt was read in 79.5 s. Decode here is a 256-token answer on code and docs, a different
text from the bench's 600-token answers, so the two decode columns are not the same measure.

## VRAM (before the fork)

5090: 31,994 MiB used with the server up (about 280 MiB free for a desktop; `--vram-reserve-mib 700`
is what keeps the expert cache from taking it all). 4070 Ti SUPER: 15,754 MiB. Peak during an 80K
prompt and during vision requests stays inside those figures; the expert cache lends slots to the
prompt path instead of allocating more.

## PR updates, prefix cache and headroom 4 (2026-10-06, the shipped config)

Patches 16-25 on the 0.1.39 series, ISTA GSQ-RCO IQ3_XXS with a runtime control vector (speed-neutral).
New binary against the previous one, same config (headroom 14), interleaved boots: decode 177-180, 2K
~610, 16K 1,440-1,464, 80K 2,224-2,254 tok/s, steps 3.2 / 3.4 / 4.6 s on both.

Headroom and parking, one boot each, `tools/parking_check.py`, `tools/depth_bench.py` (27K and 36K of
real text), `tools/step_times.py` (two texts) and `tools/bench.py`; faults = system major faults over
the run:

| | 27K / 36K fresh | 2K | 16K | 80K | follow-up on 80K | decode | parking switch | faults |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| headroom 14, parking 6 GB (before) | 1,643 / 1,643 | | | | | | 0.4-0.5 s | |
| headroom 2 | 2,800 / 2,502 | 598-617 | 2,182 | 3,221 | 5.6 s | 177 | | |
| headroom 2, parking floor 1024 | 2,895 / 3,000 | 269-490 | 2,110 | 3,077 | 4.5 s | 182 | 0.3-0.9 s (first two 12-13 s) | |
| headroom 4, parking 6 GB, floor 1024 | 2,647 / 2,850 | 336-546 | 1,911 | 3,133 | 5.9 s | 188 | 0.4-0.7 s | 199K |
| headroom 4, parking 3 GB, floor 1024 | 2,832 / 2,067 | 569-581 | 2,181 | 2,750 | 4.1 s | 176 | 0.4-2.0 s | 148K |
| **the same, rerun (shipped)** | **2,842 / 2,836** | 492-565 | **2,020** | **2,743** | 4.6 s | **179** | 0.5-1.1 s | 112K |

Parking answers right on every row (8/8). Tool steps on the shipped row: 1.6K / 2.9K / 4.2K tokens
3.4 / 3.6 / 4.0 s median, with one step in about nine at 4.5-6.3 s (page faults). Refill of the lent
slots after a prompt: 6.07 s at headroom 14, 0.14 s at headroom 4. The engine had 5.6-6.8 GB in zram
after the runs at headroom 4.

`--prefix-cache-dir`: a 20K system prompt after a restart 0.63 s (cold read 11.65 s), needle right.
Rejected: `--expert-cache-per-layer` (#934): 16K 2,042 / 80K 2,519 tok/s, but decode 102 and tool
steps 4.8 s. `STRATA_DF_BRANCH=1 STRATA_ATTN_MERGE_V2=1`: +2-3% decode (228 vs 220 median over 20
answers of 1,500 tokens), left off for the upstream hang report.

Real use on the shipped config (an agent session from another machine, one evening): turns of a chat
growing from 160K to 204K tokens read 21-3,578 new tokens in 0.2-3.7 s, decode 124-190 tok/s; full
re-reads of 147K-176K tokens ran at 3,670-3,830 tok/s (39-50 s); these happened only when a second
conversation ran in between and the long one (snapshot 3.3-3.8 GB) could not park in 3 GB.
