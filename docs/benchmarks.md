# Benchmarks

All on 2026-10-02 (the last section 2026-10-03), RTX 5090 + RTX 4070 Ti SUPER (x1), 31 GB RAM, Arch
Linux, Strata 0.1.33 (0.1.37 in the last section), ISTA GSQ-RCO IQ3_XXS, 262,144 context, layer split
36, int8 KV with 32,768 resident cells, vision on.
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

## `pread` expert copies (patch 03), chunk 32768, back to back

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

The same three patches on v0.1.37, pread on, chunk 32768, spec-min-p 0.8; MMQ and the fused kernels
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

## VRAM

5090: 31,994 MiB used with the server up (about 280 MiB free for a desktop; `--vram-reserve-mib 700`
is what keeps the expert cache from taking it all). 4070 Ti SUPER: 15,754 MiB. Peak during an 80K
prompt and during vision requests stays inside those figures; the expert cache lends slots to the
prompt path instead of allocating more.
