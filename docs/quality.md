# Output quality

Speed is only worth having if the model still computes the same thing. These checks were run 2026-11-10 on the
shipped config (Unsloth Dynamic v3.1 UD-IQ3_XXS, Unsloth's Q8_0 PLE table, layer split 39, int8 K/V, both cards).
The refusal-direction control vector is off unless a row says otherwise. One run per row.

## Summary

- **Perplexity matches llama.cpp on the same files within 0.12%**, and an independent engine (NInfer) within 0.22%
- **Strata is not token-for-token llama.cpp:** it picks a different most likely token on about 5% of positions,
  with this repository's tuning switches or without them. That gap belongs to the engine, not to the patches
- **The tuning switches are not bit-exact:** tuned and untuned agree on 96.7% of top tokens at equal perplexity
  (3.2115 against 3.2118). They reorder the same math, and on a 3-bit quant rounding flips near-ties
- **The engine is deterministic:** two runs of the same settings write byte-identical log-probabilities
- **LiveCodeBench v6 (175 problems), thinking off:** 109 / 175 = 62.3%, against 118 / 175 = 67.4% for the hosted
  Qwen3.8 Flash API. The gap is inside the noise of 175 problems (p = 0.12)

## Against llama.cpp, same files

WikiText-2 raw test, `llama-perplexity` defaults (512-token chunks, the second half of each chunk scored), the first
100 chunks = 25,500 scored tokens. llama.cpp at f86e5d114 with `-ngl 99 -ts 37,11 -ncmoe 21`, F16 K/V. KL is
KL(reference || run) over the reference's 64 most likely tokens.

| Run | Reference | Perplexity | Same top token | Mean KL | KL p99 |
| --- | --- | ---: | ---: | ---: | ---: |
| llama.cpp | | 3.2079 | | | |
| llama.cpp, 9 more expert layers on the CPU | llama.cpp | 3.2086 | 100.00% | 0.00000 | 0.00004 |
| This build, shipped switches | llama.cpp | 3.2115 | 95.11% | 0.0191 | 0.204 |
| This build, FP16 K/V | llama.cpp | 3.2103 | 95.08% | 0.0197 | 0.218 |
| This build, tuning switches off | llama.cpp | 3.2118 | 95.20% | 0.0199 | 0.212 |
| This build, shipped switches | this build, switches off | 3.2115 | 96.67% | 0.0099 | 0.114 |
| This build, int8 K/V | this build, FP16 K/V | 3.2115 | 96.72% | 0.0093 | 0.109 |
| This build, the same run twice | itself | 3.2115 | 100.00% | 0 | 0 |

- "Tuning switches off" removes these from the config's `env`: `STRATA_GR_NORM_FAST`, `SCORES_HALVE`, `TOPK_SPLIT`,
  `QIL`, `SIDE_MIXER`, `ATTN_DAILY`, `GU_SWIGLU`, `GR_UP75`, `GR_DOWN_TG`, `GR_V3`, `FUSE_HEAD_GR`, `LFUSE`,
  `PF_FUSED`, `PL_PLE_PREFETCH`, `PL_PLE_LATE`, `PL_EARLY_CHAIN`, `PM_MTP_BATCH`
- For scale, upstream's own table (`docs/QUANTS.md`, against Q8_0) puts UD-Q6_K_XL at a mean KL of 0.033 and
  UD-IQ4_XS at 0.101: the engine gap (0.019) and the switches (0.010) are both below one quant step
- Not measured: the control vector on against llama.cpp, and upstream's stock build on these chunks

## Against NInfer, same weights

WaveCut's [NInfer repack](https://huggingface.co/WaveCut/Qwen3.8-Flash-Next-UD-IQ3_XXS-NInfer-v3) of the same
UD-IQ3_XXS release reports a perplexity over the first 40 KB of the WikiText stream in `iamwavecut/ninfer-all`
(`eval/corpora/perplexity-1m/data/wikitext/00.txt`). The first 40,960 bytes are 9,451 tokens, the 9,450 targets
their card states.

| Run | Perplexity |
| --- | ---: |
| NInfer (their card), IQ4_NL PLE table, int8 K/V | 1.933029 |
| This build, control vector off | 1.928809 |
| This build, as served (control vector on) | 1.935252 |

- Protocol assumed from `ninfer-perplexity`'s defaults (their card does not state it): 4,096-token windows, 2,048
  stride, every window from empty state
- The PLE table differs (Q8_0 here, IQ4_NL there); the IQ4_NL table was not run here
- The low value is WikiText being in the training data: this checks two engines agree, it is not a quality score

## LiveCodeBench

The 175 problems added in release v6 (`test6.jsonl` of `livecodebench/code_generation_lite`, contests 2025-01-04
to 2025-04-06), the harness's generic chat prompt, one answer per problem, temperature 0, thinking off, 16,384 max
tokens, graded by the harness's own checker (6 s per test) in a container without network.

| | Easy | Medium | Hard | All |
| --- | ---: | ---: | ---: | ---: |
| Qwen3.8 Flash on OpenRouter (Alibaba, the only provider) | 41 / 43 | 42 / 52 | 35 / 80 | **118 / 175 (67.4%)** |
| This build, as served | 42 / 43 | 35 / 52 | 32 / 80 | **109 / 175 (62.3%)** |

- Per problem: both solved 100, only the API 18, only this build 9, neither 48. An exact McNemar test on the 27
  problems they disagree on gives p = 0.12
- Six hard API answers hit the 16,384-token cap and count as failures (this build had solved two of them); without
  those six it is 118 against 107 of 169. No answer of this build hit the cap
- This build wrote 512K answer tokens in 34.5 minutes of generation (247 tokens per second); the API wrote 837K
- What differs between the rows: the 3.5-bit quant, the control vector, the Sharp chat template, and possibly the
  weights (the API model is described as based on Qwen3.8-Flash-Next). It does not isolate the speed work: that
  needs the same quant in another engine on these problems, which was not run
- Not comparable to published leaderboard numbers: those use thinking, 10 samples at temperature 0.2 and often the
  whole 1,055-problem release

## Reproducing

```bash
# 1. llama.cpp: perplexity and its log-probabilities for 100 chunks (12.7 GB file)
llama-perplexity -m UD-IQ3_XXS/...-00001-of-00004.gguf -f wiki.test.raw --chunks 100 \
  -ngl 99 -ts 37,11 -ncmoe 21 --kl-divergence-base llama-100.logits

# 2. this build on the same tokens: copy the running engine's command line, stop the server, score
tools/engine_logprobs.py capture engine.json
tools/engine_logprobs.py run engine.json strata-100.tsv --logits llama-100.logits --no-cvec
tools/engine_logprobs.py vs-llama llama-100.logits strata-100.tsv

# 3. NInfer's protocol
tools/engine_logprobs.py ids wikitext-00.txt 40960 strata/packs/<pack>/tokenizer strata ids.json
tools/engine_logprobs.py run engine.json windows.tsv --ids ids.json --no-cvec
tools/engine_logprobs.py ppl windows.tsv 9451

# 4. LiveCodeBench (the grader runs model-written code: see the container command in tools/lcb_grade.py)
tools/lcb_gen.py out/run.jsonl --data data/test6.jsonl --max-tokens 16384
LCB_AUTH=<key> tools/lcb_gen.py out/api.jsonl --data data/test6.jsonl --max-tokens 16384 --workers 24 \
  --url https://openrouter.ai/api/v1 --model qwen/qwen3.8-flash --openrouter
```

- llama.cpp needs the PLE table as the release's fourth shard: stamp Unsloth's standalone table with their
  `engram/set_split.py` (4 of 4) and put it in the shard's place, on an unpatched copy of the file
- `engine_logprobs.py run` starts a second engine, so the server has to be stopped first
