# Earlier measurements

Numbers that used to sit in the README, kept as they were written. The current config's numbers are in the
[README](../README.md#performance); every run in detail is in [benchmarks.md](benchmarks.md).

## Upstream's own benchmark suite (v0.2.1 build, IQ3_S config, 2026-10-23)

`tools/strata_bench.py --long` from Strata v0.2.1 against the running server (the shipped config, thinking off,
temperature 0, 3 runs per test, medians with ranges). Full report:
[docs/strata-bench-2026-10-23](strata-bench-2026-10-23/README.md).

| Test | Prompt tokens | Prompt tok/s | Decode tok/s | First token (s) |
| --- | ---: | --- | --- | --- |
| short chat | 200 | | 186.3 (153.7-254.8) | 0.28 (0.27-0.52) |
| 4K prompt, fresh | 4,024 | 2,446 (1,909-2,830) | | 1.66 (1.44-2.12) |
| 16K prompt, fresh | 16,056 | 3,917 (3,913-4,000) | | 4.12 (4.04-4.12) |
| 32K prompt, fresh | 32,049 | 4,159 (4,150-4,206) | | 7.74 (7.65-7.75) |
| agent session, follow-up turns | up to 14,881 | | 173.5 (145.3-201.5) | 1.31 (0.81-1.79) |

Agent session cache hit 70.0 % (the rest is the new file text of each turn, read once).

## Long prompts on the v0.2.1 build (2026-10-23, fresh boot)

| Prompt | Prompt time | Decode after it | Read from the SSD |
| --- | --- | --- | --- |
| 80K random words | 19.0 s | 153-161 tok/s | 4.7-5.1 GB |
| 149K random words | 31.6-32.6 s | 146-152 tok/s | 8.7-9.0 GB |
| 183K of C++ source | 48.6-49.1 s | 177-186 tok/s | 4.0-4.2 GB |

One thing a fresh boot does not show: an agent conversation that grows past ~160K tokens slows decode on
31 GB of RAM (84 tok/s at 160-200K, 34 tok/s at 200K+ in one long session), and the expert placement it leaves
behind stays slow for short prompts too until a restart (18-22 tok/s, 87% GPU hits; 232-272 tok/s after the
restart). Compact long chats before ~150K. Details: [docs/benchmarks.md](benchmarks.md).

## The v0.1.41 build (history)

### The shipped config (IQ3_S) and the IQ3_XXS alternative

Same engine, same settings except the quant and its prompt chunk, measured 2026-10-10 on this box
(`tools/bench.py`, `tools/depth_bench.py`, `tools/step_times.py`; the probes and the tool-call runs on the
dates given in [docs/benchmarks.md](benchmarks.md)):

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
| **Sharp at xhigh, our parser fix (old patch 08, now in 01)** | **44/60** | 9 `bash` calls never written, 5 `new_string` never written, 2 turns ended inside the thinking |

Every remaining miss is the model's: the raw engine output shows the call was never written. The model also
writes `<parameter=limit>25</parameter>` and then skips the value's own closer in about half of these edits;
the parser fix reads that correctly, which is the 17 -> 0.

Every run, A/B and rejected knob: [docs/benchmarks.md](benchmarks.md).
