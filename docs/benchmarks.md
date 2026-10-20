# Benchmarks

All on 2026-10-02 to 2026-10-15, RTX 5090 + RTX 4070 Ti SUPER (x1), 31 GB RAM, Arch Linux, ISTA GSQ-RCO
IQ3_XXS until 2026-10-10 and IQ3_S since (the shipped quant), 262,144 context, layer split 36 (37 since 2026-10-07), int8 KV with 32,768 resident cells, vision on. The Strata base
moves through the sections: 0.1.33, 0.1.37, 0.1.38 with six PRs, the Strata-DualGPU fork, then the fork's later commits with the
lend region in RAM, then upstream 0.1.39 with the fork's work as PRs, then the 2026-10-06 PR updates with headroom 4, then upstream 0.1.40.1 with the SSD spill, then upstream 0.1.41 with the draft K/V on the main device, the quant comparison, IQ3_S, and the template and parser work (the last five sections, the shipped config).
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

## Upstream 0.1.37 base and `STRATA_PF_FUSED=1` (2026-10-03)

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

## PR updates, prefix cache and headroom 4 (2026-10-06)

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

### Depth table on the shipped config (2026-10-06)

`tools/depth_bench.py` as above, same corpus (Strata's source, now with patches 16-25), on the server
under its normal load; run in two parts (2K-62K, then 92K-260K) because the first run was stopped at
92K by a memory-pressure guard in the client tooling, not the server.

| depth | prefill | prefill, headroom 14 (2026-10-05) | decode |
| --- | --- | --- | --- |
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

The 260K prompt was read in 85.3 s (79.5 at headroom 14). Headroom 4 wins clearly up to 92K and
not past it: chunks of the longest prompts borrow beyond what locked RAM covers in both configs, and
with about 1 GB available the engine pays more page faults. Decode is unchanged.

## Upstream 0.1.40.1, split 37, the SSD spill and PR #1269 (2026-10-06 night to 2026-10-07, the shipped config)

Same corpus and tools as the section above. The new binary against the 0.1.39 build, same evening, split
36, parking 1024 with the spill: decode median 198 vs 179, 2K 448-584, 16K 2,158 vs 2,020, 80K 3,133 vs
2,743, follow-up 4.1 vs 4.6 s, 27K 2,820 tok/s, tool steps 3.2 / 3.4 / 3.9 s; engine memory in zram 3.5
GB vs 5.6-6.8. Needle, merged tool turns and images all right.

Layer split, with the image encoder moved to the 4070 (`"vision": {"cuda_device": 1}`):

| split | GPU-cached experts | locked RAM | decode | 2K | 16K | 80K | follow-up |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 36, encoder on the 5090 | 14,951 | 15.13 GiB | 198 | 448-584 | 2,158 | 3,133 | 4.1 s |
| **37, encoder on the 4070** | **16,014** | **14.28 GiB** | 195 | **631-646** | 2,117 | 3,192 | 3.9 s |
| 38, encoder on the 4070 | 15,849 | 15.39 GiB | 191 | 480-493 | 2,179 | 3,290 | |

At split 36 the encoder does not fit on the 4070 next to the drafter (the boot fails). Parking 8/8 right
on split 37, image requests right.

The SSD spill (`tools/spill_check.py`: a 199K conversation with a needle and a 5K one, alternating, four
rounds): before it, every switch back to the long chat re-read it (~47 s). With the spill the 3.1 GB
file is written in 1.6-2.5 s and read back in 2.7-3.9 s; every answer right.

PR #1269 (streamed restore) plus our patch 19, same session, the old binary as control, page faults
counted over rounds 1-3 only:

| | switch back to 199K | switch back to 5K | lowest available RAM | major faults | swap-ins | engine faults |
| --- | --- | --- | --- | --- | --- | --- |
| whole file read into RAM (control) | 2.7-3.9 s | 0.4-0.5 s | 225 MiB | 18,331 | 18,055 | 6,464 |
| **streamed in 16 MiB blocks** | 3.0-3.2 s | **0.2 s** | **2,531 MiB** | **218** | **31** | **4** |

The streamed restore reads the file twice (validate, then apply), about 0.3 s more; in exchange nothing
is pushed out to swap, and the 5K chat stays parked in RAM instead of going to the SSD too. Bench on the
shipped build: decode 188, 2K 646-655, 16K 2,284, 80K 3,281 tok/s, follow-up 4.1 s.

Tested and not adopted, same morning against a control boot of the same binary: PRs #1101 (stager
threads sleep instead of spinning), #1237 (pinned stage buffers), #1181 (linear verify-window plan) and
#1288 (a long read yields by what is left to read). Decode, prompts, tool steps and engine CPU time
(361-384 s per `bench.py` run vs 382 s) all within noise on this box.

### Depth table on the shipped config (2026-10-07)

`tools/depth_bench.py`, corpus = the v0.1.40.1 source with the patches, run in three parts. Raw time to
first token, and the spill write of the previous conversation that preceded it (from the server log):

| depth | TTFT | spill write before it | prefill without the write | decode |
| --- | --- | --- | --- | --- |
| 2K | 3.5 s | | 553 tok/s | 170 tok/s |
| 32K | 16.5 s (reruns 8.1 / 11.0 s) | | 1,933 (reruns 3,939 / 2,911) | 159-165 tok/s |
| 62K | 15.3 s | (32K parked in RAM) | 4,040 tok/s | 150 tok/s |
| 92K | 23.6 s | 62K, 1.1 GB, 0.7 s | 4,018 tok/s | 151 tok/s |
| 122K | 32.0 s | 92K, 1.6 GB, 0.9 s | 3,924 tok/s | 149 tok/s |
| 152K | 41.5 s | 122K, 2.0 GB, 1.2 s | 3,766 tok/s | 142 tok/s |
| 182K | 55.4 s | 152K, 2.4 GB, 6.8 s | 3,741 tok/s | 140 tok/s |
| 212K | 71.8 s | 182K, 2.9 GB, 9.3 s | 3,393 tok/s | 147 tok/s |
| 242K | 81.3 s | 212K, 3.3 GB, 13.2 s | 3,552 tok/s | 139 tok/s |
| 260K | 102.0 s | 242K, 3.8 GB, 18.9 s | 3,127 tok/s | 140 tok/s |

In this run the spill write was synchronous: the next conversation waited for it. The SSD (WD SN740, 94% full) takes
the first ~5 GB of a burst at about 1.7 GB/s and then drops to 170-360 MB/s, so eight long chats in a
row (21 GB of spill files) is the worst case; a single switch writes in 1-2.5 s. A 32K rerun right after
the 260K prompt waited 24 s for its 4 GB write and then read slowly too (54.3 s in total).

### The spill written while idle (patch 20, 2026-10-07)

Same morning, one boot, a scripted sequence (`thinking off`, greedy, needles in each conversation):

| step | prompt | time | spill log |
| --- | --- | --- | --- |
| A, fresh | 152K | 43.1 s | 2 s later, idle: A written (2.4 GB) in 1.4 s |
| B, fresh (A does not park) | 5K | 4.2 s | A's file kept, nothing written |
| A, follow-up | 152K | 2.5 s | read back from the file |
| C, fresh | 121K | 38.9 s | A's file kept (28 tokens behind) |
| C, follow-up 3 s after the answer | 121K | 0.3 s | the idle write of C gave way after 436 ms |
| B again, 15 s later | 5K | 0.2 s | C written while idle (2.0 GB, 2.9 s) and kept |

Every answer right. Before patch 20, B's fresh prompt would have waited for A's 2.4 GB write. After the
server stopped (SIGTERM, which sends QUIT to the engine) the spill directory was empty; a cancelled write
left no temporary file.

## Upstream v0.1.41 and the draft layer's K/V on the main device (2026-10-08)

The whole series merged onto v0.1.41 (now patch 01), IQ3_XXS, the same config, against the v0.1.40.1 build
in the same session (`tools/bench.py` run 2; run 1 is the cold one):

| | v0.1.40.1 build | v0.1.41 build |
| --- | --- | --- |
| decode median | 199 | 203 |
| 2K | 606 / 454 | 643 / 644 |
| 16K | 2,080 | 2,315 |
| 80K | 2,793 | 3,359 |
| 80K follow-up | 3.7 s | 3.8 s |
| depth 32K / 122K / 260K prefill | 3,091 / 3,307 / 3,870 tok/s | 3,128 / 3,774 / 2,907 tok/s |
| lowest available RAM over the depth run | 1.0 GB | 3.2 GB |

The 260K gap is disk state: the new tree's spill directory already held 11-15 GB on the 92%-full SSD, so its
122K spill write took 13 s instead of 1.9. Needle 40K + 4 follow-ups + 60K extension, parking 8/8 (0.9-1.1 s),
spill 200K / 5K x4 (2.9-3.0 s / 0.2 s), the merged tool turn, the 14:05 train, vision on the 4070 (1.9 s) and
tool steps 3.0 / 3.2 / 3.9 s all passed on the new build.

**The draft layer's prompt K/V computed on the 5090 (patch 04)** against the residual-rows path it replaces,
same session, fresh prompts, prefix cache cleared between arms:

| | 40 KB/token of rows over the x1 link | K/V computed on the 5090, K/V rows shipped |
| --- | --- | --- |
| `after each chunk` on an 82K prompt (link traffic) | 4.0-4.3 s | 0.27-0.30 s |
| the same on a 32K prompt | 1.7 s | 0.08 s |
| TTFT 32K / 40K / 48K / 56K / 82K | 9.9 / 14.0 / 12.6 / 15.0 / 21.3 s | 9.0 / 9.4-12.5 / 10.4 / 11.3 / 16.8 s |
| bench 16K / 80K prompt | 7.5 / 25.9 s | 6.5 / 21.0 s |
| decode median (session band 174-195) | 195 | 187-190 |
| 1024-token answers after 40-56K prompts | 145-152 tok/s | 157-160 tok/s |
| draft acceptance over 1024-token answers | 78.5% | 78.9% |

Two traps on the way, both visible only as lower acceptance, never as an error: a synchronous peer copy does
not wait for a non-blocking compute stream (acceptance 64-67% from partly stale K/V), and the next batch's
kernels overwrote the staging source while the previous copy over the x1 link (16 MiB, ~20 ms) was still
reading it (4.7 points low). An explicit stream sync before the copy and an event the compute stream waits on
fixed them. Upstream's PR #1599 (patch 03) is inert under `--prefill-main`: the drafter sits on the other
device and its block declines. The PR's parity tool reports FAIL even between two single-GPU arms here (the
target's tokens shift with the verify window's row grouping), so acceptance over 1024-token answers and the
`after each chunk` line are the gates.

## Quants on the same config (2026-10-10)

The production config with only the model paths changed, same bench, same session:

| arm | GPU-resident experts | decode median | 2K | 16K | 80K | 80K follow-up | decode at 82K | acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ISTA IQ3_XXS (the build's quant until then) | 21,752 of 24,576 | 181 | 3.4-3.6 s | 6.6 s | 21.1 s | 3.9 s | 146 | 81.3% |
| ISTA Q2_0 | 24,576 (all) | 211 | 2.5-2.6 s | 5.9 s | 19.6 s | 3.1 s | 158 | 82.7% |
| unsloth UD-IQ4_XS | 15,340 | 58 | 5.1-5.4 s | 13.1 s | 43.1 s | 6.5 s | 82 | 80.4% |
| **ISTA IQ3_S** | 18,620 | 171.7 aggregate / 181 median | 3.9-7.8 s | 7.0 s | 26.9 s | 4.8 s | | 84.5% |
| **IQ3_S, `--prefill auto:16384` (shipped)** | 18,620 | 168.9 / 198 | 3.7 s | 7.2 s | 25.9 s | 6.6 s | | |

unsloth's file is 93.7 GB: RAM is fully used, decode reads about 5,000 expert blobs per answer from the SSD, and
no knob fixes a 3x gap on 31 GB (headroom 2 and `--prefill auto` reached 70-73 tok/s). Q2_0 holds every expert
in VRAM and is the speed pick at a quality cost (ISTA task average 89.07 vs 92.57 for IQ3_XXS). IQ3_S has about
3,000 fewer GPU-resident experts than IQ3_XXS, yet decode still reads 0 experts from the file (the RAM copy is
17.0 GiB at headroom 4); with 32K chunks 41% of a chunk's lent slots re-read from the pack, with 16K chunks all
2,813 lendable slots stay in RAM, a wash on speed and cleaner on RAM. Quality evidence is external only:
sirfyyn's KL divergence from BF16 over three corpora puts UD-IQ4_XS at 0.049 / 0.046 / 0.122, IQ3_S at
0.069 / 0.061 / 0.183 and IQ3_XXS at 0.118 / 0.112 / 0.264; ISTA's own task average is 93.26 (IQ3_S) and 92.57
(IQ3_XXS) against 93.12 for BF16. IQ3_S is the shipped quant since 2026-10-10.

**IQ3_S full suite on the shipped config (2026-10-10):** needle 40K with four follow-ups and a 61K extension
all correct (15.0 s read, follow-ups 0.2-0.5 s, the extension 10.8 s); parking 8/8 (30K / 15K, switches
0.7-1.4 s); spill 200K x4 (61.4 s read, restores 2.8-2.9 s, the short chat 0.2 s); the merged tool turn's four
steps; an image read through the 4070's encoder in 3.7 s; tool probe 16/30 (stock template); depth 32K 10.2 s
(3,124 tok/s) then 134.7 tok/s, 122K 35.1 s (3,479) then 131.0, 260K 76.4 s (3,405) then 124.2; tool-result
steps of 1.5K / 2.3K / 5.4K tokens 3.2-3.6 / 3.4-3.6 / 3.8-4.2 s after a 12.9K first message (5.1 s).
Basalt's self-distilled draft layer as a drop-in drafter: acceptance 86.1% vs 85.7%, not adopted.

## Tail skip and RAM adapt (2026-10-10)

Upstream's 0.1.42 `STRATA_ROUTE_TAIL_SKIP` (patch 05) cherry-picked: a missed expert that every token of a verify
window routes at rank 7 or lower is neither copied nor computed. Same session, same binary, milliseconds per
verify window paired over 13 requests (the measure that survives acceptance noise; tok/s swings 0.73-0.88
acceptance between identical runs here):

| | off | rank 7 (now the default) | rank 7 + `STRATA_RAM_ADAPT=256` |
| --- | --- | --- | --- |
| IQ3_S ms/window, aggregate tok/s, bench median | 13.22, 170, 167 | 12.78 (12 of 13 wins), 174, 180 | |
| unsloth UD-IQ4_XS ms/window, aggregate, bench median | 31.1, 72.3, 79 | 24.1 (13 of 13), 93.1, 103 | 21.7, 101.4, 109 |

Prompts unchanged; the probes (planets, the 14:05 train, two needles in 98K, a haiku follow-up) pass; answers
differ slightly (upstream measured KL 0.003-0.006). `STRATA_RAM_ADAPT` (PR #1838, opt-in) lets the RAM copy
follow the conversation between requests: on the SSD-bound unsloth quant fresh prompt sets went 73.9 / 76.2 ->
88.5 / 89.2 tok/s and file reads per eight answers 53 / 47 -> 34 / 31 GB; on IQ3_S decode reads nothing from
the file, so it does nothing and the shipped config leaves it unset.

## The park gain (PR #2265, 2026-10-13)

Upstream issue #2264: the conversation cache parked every turn and the next turn dropped the snapshot, so a
long single conversation wrote a whole snapshot per turn for nothing. One day of the production log: 1,131
parks for 93 restores, 294 GB written, 112 s spent on the request path. `--conversation-cache-park-gain 4096`
(patch 05) parks again only once the conversation grew by 4,096 tokens. Judged by parks versus restores in the
log, not by an A/B. `--mtp-hnorm stream` (upstream's opt-in drafter norm) went on the same day; first probes at
temperature 0 with thinking off: code 237, prose 146, reasoning 194 tok/s at 91 / 78 / 83% acceptance.
Tested the same day and rejected: `STRATA_EXPDEC=1 STRATA_QSA_ROWS=1` (PRs #2058 / #2059), interleaved
off/on/off/on, ms per window code 14.00 -> 14.39, reasoning 12.92 -> 13.37, 110K context +1.1%.

## The chat template and the tool-call parser (2026-10-15, IQ3_S)

`tools/tool_probe.py` (the two-turn agent probe: parallel `read_file` calls with integer arguments, then an
`edit_file` whose strings hold a literal `<parameter=limit>..</parameter>` line, plus a `bash` call), 15
sequences per run, the same seeds.

Templates, same server, stock parser:

| template | pass | note |
| --- | --- | --- |
| stock Qwen (Unsloth's, xhigh default) | 21/60 | |
| Sharp v22.5.0 at its medium default | 8/60 | empty `new_string` 2 -> 15 |
| Sharp with `reasoning_effort: xhigh` per request | 33/60 | |

Effort level drives the calls; the terseness block does not hurt them. Ten short questions: Sharp used a third
of the tokens with equal accuracy. A "pelican on a bicycle" SVG: Sharp at medium 2.4K / 4.7K tokens, stock
8.4K / 18.4K. The shipped tokenizer directory is Sharp with its default raised to xhigh.

The parser (patch 08), Sharp at xhigh, same engine, 4 x 15 sequences each:

| | pass | edit cut at the nested `</parameter>` | `bash` never written | `new_string` never written | turn ended inside the thinking |
| --- | --- | --- | --- | --- | --- |
| stock parser | 30/60 | 17 | 14 | 6 | 1 |
| patch 08 | **44/60** | **0** | 9 | 5 | 2 |

The raw engine output (`STRATA_DEBUG=1`) shows the cause: in 7 of 15 edits the model writes
`<parameter=new_string>\n<parameter=limit>25</parameter>\n</function>`, the inner closer standing in for the
value's own, which the old rule (the first `</parameter>` followed by `<parameter=` or `</function>`) read as
`new_string = "<parameter=limit>25"`. Every remaining miss is a call the model never wrote. All 45 raw outputs
captured that day parse correctly with the patch at chunk sizes 1 / 3 / 7 / 50 / whole, streamed and not.
PRs #2589 and #2572 (patches 06, 07) were measured the same day with `tool_call_recovery` on: 32/60, noise; the
recovery rewrote 0 parameter tags (this model never writes `<parameter name=`) and invented a call named
`new_string` once, so it stays off.

## Config sweep, the commit graph and the lend ring (2026-10-15 evening, IQ3_S)

Metric: milliseconds per verify window, `timings.predicted_ms / (predicted_n - draft_n_accepted)` from the chat
response, over 7 short prompts (3 code, 2 reasoning, 2 prose, 600 tokens, temperature 0, thinking off) and one
~20K-token prompt (300 tokens); one fresh boot per arm, the baseline booted twice (`tools/window_bench.py`).

| arm | ms/window median (7) | code / 20K context | tok/s median (7) |
| --- | --- | --- | --- |
| split 37 (the config until then), two boots | 12.37 / 12.35 | 12.1-12.2 / 12.4-12.8 | 221 / 215 |
| **split 38**, two boots | **12.10 / 12.20** | **11.5 / 11.9-12.1** | 229 / 224 |
| split 39 | 12.04 | 11.9 / 12.45 | 213 (the 4070 idles 1.1 GB emptier for nothing) |
| `--mtp-hnorm pooled` (the default) | 12.62, acceptance 83.5 vs 86.5% | | 200 |
| `--pipeline-windows 1` | 16.40 | | 180 |
| `--spec 3` / `--spec 5` | tok/s is the gate for K: 214 / 198 vs 215-221 | | 6 not run |
| `--spec-min-p` 0.85 / 0.9 / 0.95 (paired, see below) | ratio to 0.8: 1.003 / 0.995 | | a no-op |

Split 38 is the shipped value: one layer fewer on the 4070 shortens the serial sum (a layer costs ~0.22 ms on the
5090 and ~0.37 ms on the 4070 per window). Fresh-prompt prefill is at parity (81K: 29.0 / 25.5 / 25.6 s on 37 vs
29.2 / 25.9 / 26.7 on 38; 203K: 65.9 vs 59.9 s, one sample each) and decode after those prompts is better on 38
(130-157 vs 148-168 tok/s). Noise between identical boots: ms/window +-0.05 on short prompts, +-0.4 at 20K; the
prompt-read seconds swing 20-27 s on the same config (page faults), so they are not a gate.

`--spec-min-p` first measured as +6-8% at 0.9, twice, and that was the measurement: the first request after a
fresh prompt runs 10-15% slower (the prompt read and the refill of the lent expert slots), so an A/B that sends its
arms in a fixed order per prompt flatters every arm but the first. With a settle request per prompt and the arm order
rotated, 0.8 / 0.9 / 0.95 are equal: a higher value raises the acceptance (84 -> 89 -> 91%) and shortens the windows
by the same amount; 1.0 collapses the drafts (-25%). `tools/paired_ab.py` is that protocol.

**The commit graph in one launch (patch 09, upstream `STRATA_COMMIT_BATCH`, default on):** same binary, the kill
switch as the off arm, one boot each: on 12.08 ms/window, 20K context 11.62, 231 tok/s; off 12.16 / 12.27 / 219.
Bitwise identical per upstream's parity tools, so it stays on.

**The lend ring decided before the regions are sized (patch 10):** inert on this config. The new start line reads
"the prompt path borrows 2837 slots (ring 96 slots at chunk 16384), 2837 of them keep their experts in RAM too" and
CUDA0 keeps the same 858 slots as before, because the series' own lend-in-RAM sizing already matched the ring. Prompts
unchanged (81K 24.5-29.0 s, 203K 61.9 s). The NVMe counter added to the harness puts the prompt path's file reads at
60-64 GB per 81K prompt and 157 GB per 203K: the 4070's layers re-streamed per 16K chunk under `--prefill-main`
(see the 2026-10-08 note), not the ring.

Not built, on the evidence: a per-device `--kv-resident` so the 4070's three attention layers keep their whole KV
in VRAM. The KV-streaming hit rate on the 4070 is 99.7% at short context and 93-94% at 203K, where it reads
~100 MiB per 300-token answer over the x1 link: about 0.6 ms of a 12 ms window, and nothing below ~100K tokens.

## The later stage's K/V whole in VRAM (patch 11, 2026-10-15 night)

`--kv-resident-later 0` on split 39 (the 4070 needs ~0.7 GB for the three layers' K/V; at split 38 it has 0.65 GB
spare and would lose experts), same engine, one boot per arm, `tools/window_bench.py` twice per arm:

| arm | ms/window median (7) | 20K context | 81K prefill x3 | 203K prefill | decode after 81K / 203K |
| --- | --- | --- | --- | --- | --- |
| split 38, streamed (the config until then) | 12.08 | 11.62 | 24.5 / 29.0 / 24.5 s | 61.9 s | 150-166 / 152 tok/s |
| split 39, streamed | 12.04 / 12.13 | 12.45 / 11.97 | | | |
| **split 39, `--kv-resident-later 0`** | 12.44 / 12.24 | **11.89 / 11.66** | **22.9 / 23.9 / 23.5 s** | **57.2 s** | **159-176 / 165 tok/s** |

Short prompts pay about 0.2 ms per window (the attention layers' resident pools are 8x larger than the streamed
window; not traced further). From 20K context on it wins, and the long-prompt gains are the point: the 4070 reads
no K/V over its x1 link during decode (its counter used to show 93-94% VRAM hits and ~100 MiB per 300-token answer
at 203K), and split 39 re-streams one 4070 layer fewer per prompt chunk (NVMe reads 60-64 -> 47-50 GB per 81K
prompt, 157 -> 124 GB at 203K). Costs: the 203K-token hand-off to the 4070 after a fresh prompt or a restore
crosses the link once (restores 2.8-2.9 -> 3.8 s in the spill check). Correctness on the new copy path: needle
40K + four follow-ups + a 20K extension all right; the 200K spill round trip four times right (the "plus one" and
"backwards" rounds included); planets and the train problem right.

## Agent steps read split-wise (patch 12, 2026-10-15 night)

`tools/agent_steps.py`: a 13K-token first message, then follow-ups of 1.5K / 2.4K / 5.4K / 0.5K fresh tokens
(tool results), 60 tokens answered each; prompt seconds and the SSD bytes read per step, same seed on both arms,
one boot each (IQ3_S, split 39, `--kv-resident-later 0`):

| step | fresh tokens | production (whole-model) | `--prefill-main-small 512` |
| --- | --- | --- | --- |
| first message | 13,029 | 9.3 s, 12.4 GB | 5.5-6.9 s, 10-14 GB (whole-model, unchanged) |
| tool result | 1,567 | 3.3 s, 10.6 GB | **1.2 s, 0.2 GB** |
| tool result | 2,406 | 6.5 s, 10.9 GB | **1.3 s, 0.1 GB** |
| tool result | 5,419 | 3.9 s, 10.7 GB | **2.5 s, 0.3 GB** |
| short follow-up (windows) | 530 | 1.9 s, 0.1 GB | 1.9 s, 0.1 GB |

Correctness: a needle in a 15K whole read, a chained 2K follow-up that asks for it and a second needle it carries,
a 20K whole read after the chained one asking for all three, then a windows follow-up: all right. A 4 Mpx image
in a follow-up takes the whole-model path as it must, and a chained read after it is fine. Decode: four boots with
the flag read 12.43 / 12.44 / 12.62 / 12.77 ms per window against 12.34 / 12.36 / 12.52 without it, and a control
with only the 4070's reserve lowered (no stage path at all) read 12.65, so the gap is this session's boot noise,
not the path. Long whole-model reads on the shipped config after the change: 81K 24.3-25.0 s, 203K 57.7 s (before:
23-24 s, 57.2 s). The 4070 sits at ~750 MiB free with the path, the reserve 420 MiB and all its experts resident.

Where the chained read stops paying (`--prefill-main-small-max`, fresh first messages, same seeds, one boot each):
chained at 512-token chunks reads 1,880 / 2,040 / 2,500 / 2,510 tok/s at 4K / 8K / 13K / 16K with 0.4-1.0 GB from
the SSD and 2,230 / 2,210 at 32K / 64K; whole-model 16K chunks read 980 (13.4 s, 12 GB) / 2,505 at 13K / 16K and
3,005 / 3,350 at 32K / 64K (23 / 46 GB). The shipped config sets the limit to 16384. `STRATA_PREFILL_TIMING=1` shows
why the chained read flattens: the 4070 does a 512-token piece of its nine layers in 99 ms (5,170 tok/s), while the
5090 at 512-token chunks spends 25% in expert dequantisation and 16% in the gate/up GEMMs, both per-chunk costs a
16K chunk amortises 32x. Reading long prompts chained with the 5090 at 16K chunks and the 4070 consuming the
hand-off in pieces is the next step, not built.

### Every text part chained (the same night, the shipped config)

With the stage consuming a whole 16K chunk in 512-token pieces from one pinned buffer and a part cut into ~4
chunks, the chained read is the long-prompt path too (`--prefill-main-small-max 262144`). Fresh prompts, same
seeds as the table above; the 81K x3 / 203K runs are `tools/long_prefill.py`-style unique prompts:

| fresh tokens | whole-model (before) | chained, 4 chunks per part |
| --- | --- | --- |
| 4K / 8K | 2.1 / 3.5 s | 2.4 / 2.9 s |
| 13K / 16K | 13.4 / 6.4 s (12 / 11 GB SSD) | 4.0 / 5.0 s (0.9 / 1.0 GB) |
| 32K / 64K | 10.6 / 19.0 s (23 / 46 GB) | 8.6 / 15.9 s (1.9 / 3.6 GB) |
| 81K x3 | 24.3-25.0 s (54-58 GB each) | 18.5 / 20.0 / 19.3 s (4.6 GB each) |
| 203K | 57.7 s (139 GB) | 41.0 s (11.5 GB) |

Agent steps (13K first message, then 1.5K / 2.4K / 5.4K / 0.5K): 6.4 / 1.1 / 1.2 / 1.8 / 1.9 s. Needle through
whole, chained and windows reads right; the 200K spill check right in four rounds (the long one restored in 3.8-4.0 s);
a 4 Mpx image follow-up takes the whole path and a chained read after it is fine; a 120K read cancelled by the
client after 8 s leaves the conversation answerable from its last checkpoint. Decode 12.32 ms per window (the
production band 12.3-12.5). The 5090 reads its 39 layers at ~5,300 tok/s in 16K chunks and the 4070 its 9 at
~5,200 tok/s in 512-token pieces, so the pipeline is balanced; the 4070's piece size (1024 needs ~170 MiB more
VRAM than it has at split 39) and its layer count (split 40-42) are the next knobs.

