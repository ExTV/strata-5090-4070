# Community benchmark on NVIDIA GeForce RTX 5090 + NVIDIA GeForce RTX 4070 Ti SUPER

Measured on 2026-10-23 with `tools/strata_bench.py` (suite 1, 3 runs per test, medians with ranges). Speeds are the engine's own timings; first-token times are measured by the client over HTTP. Speed only: no correctness check was run.

## Hardware and software

- GPU and VRAM: NVIDIA GeForce RTX 5090 + NVIDIA GeForce RTX 4070 Ti SUPER, 48 GiB VRAM
- CPU: Intel(R) Core(TM) i7-14700K (20 cores, 28 threads); installed RAM: 31.1 GiB; storage: not measured
- OS: Linux 7.2.11-arch1-1; GPU driver: 615.78.08; CUDA: not read
- Strata: project 0.1.46, commit 90767252; engine 0.1.46
- Background workloads and power limits: not recorded

## Model and configuration

- Model and quantization: qwen3.8-flash-next-IQ3_S
- Context: 262144 tokens; parallel slots: 1
- Settings: the install's own configuration, unchanged; thinking off for the suite; temperature 0

```text
strata --pack gsq-iq3_s --native Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf --ple-gguf ple-fp8.gguf --expert-profile expert-profile.bin --expert-cache auto --mmap-experts --prefill auto:16384 --spec 4 --spec-min-p 0.8 --mtp rt --mtp-hnorm stream --max-context 262144 --kv int8 --kv-resident 32768 --kv-resident-later 0 --vision --vram-reserve-mib 700 --prefill-main --conversation-cache-mib 1024 --conversation-cache-slots 8 --conversation-cache-park-gain 4096 --resident-experts --vram-reserve-later-mib 420 --short-read 128 --trim-stage-weights --pipeline-windows 2 --adapt-async 1 --control-vector-scaled Huihui-Qwen3.8-Flash-Next-refusal-direction-r.gguf:1.0 --control-vector-layer-range 4 44 --cvec-mode project --cvec-dir per-layer --prefix-cache-dir prefix-cache-iq3s-021 --prefix-cache-ram-mib 512 --conversation-cache-min-free-mib 1024 --conversation-spill-dir conv-spill-iq3s-021 --no-conversation-spill-idle --conversation-cache-min-tokens 1024 --prefill-main-small 512 --prefill-main-small-max 262144
```

Environment of the config: `STRATA_ROUTE_TAIL_SKIP=0`, `STRATA_BLOB_PREAD=1`, `STRATA_PF_FUSED=1`, `STRATA_RESIDENT_LEND=1`, `STRATA_RESIDENT_HEADROOM_GIB=4`, `STRATA_PL_PLE_PREFETCH=1`, `STRATA_PL_PLE_LATE=1`, `STRATA_PL_EARLY_CHAIN=1`, `STRATA_PM_MTP_BATCH=1`, `STRATA_RAM_ADAPT=256`

## Method

Run by `python tools/strata_bench.py --long` against the HTTP API of a Strata server (already running); model loading is not timed. One warm-up chat and a 1K prompt are discarded first. Every prompt starts with a unique tag, so the conversation cache cannot help the fresh-prompt tests.

- short chat: the three questions of `tools/ab_engine.py`, up to 100 new tokens, 3 runs
- 4K / 16K prompts: generated word lists sized by a calibration request, 24 new tokens, 3 fresh prompts each
- agent session: system prompt and four tools, then 5 turns that each add about 1500 words of a project file and continue from the model's own earlier answers (the way agent clients resend a conversation), 64 new tokens per turn, 3 sessions; the cache numbers come from the answer's usage (`cached_tokens`) and timings (`prompt_n`)
- concurrency (when run): N requests sent at the same moment, total tokens over the wall time of the burst, latency over all requests

## Results

| Configuration | Actual prompt tokens | Reused tokens | Generated tokens | Runs | Prompt tok/s median and range | Decode tok/s median and range | TTFT seconds median and range |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| short chat | 200 (197-205) | 0 | 100 (100-100) | 9 | not measured | 186.3 (153.7-254.8) | 0.28 (0.27-0.52) |
| 4K prompt, fresh | 4024 (4024-4024) | 0 (0-0) | 24 cap | 3 | 2446.3 (1909.2-2830.4) | not measured | 1.66 (1.44-2.12) |
| 16K prompt, fresh | 16056 (16056-16056) | 0 (0-0) | 24 cap | 3 | 3916.7 (3912.8-4000.1) | not measured | 4.12 (4.04-4.12) |
| 32K prompt, fresh | 32049 (32049-32049) | 0 (0-0) | 24 cap | 3 | 4159.3 (4149.8-4206.1) | not measured | 7.74 (7.65-7.75) |
| agent session, follow-up turns | 14860 (14823-14881) at the last turn | see below | up to 64 | 3 | see below | 173.5 (145.3-201.5) | 1.31 (0.81-1.79) |

Ranges are the lowest and highest of the runs; `Runs` counts requests that returned a token.

### Agent session (conversation cache)

Cache hit over the follow-up turns: 70.0 % (69.9-70.1); earlier-turn tokens read again per session: 4 (3-74) (earlier turns that the cache did not hold; the 13826 (13825-13827) new tokens of the files are read once); first turn (nothing cached) first token: 1.03 s (1.01-1.03).

| Turn (run 1) | Prompt tokens | Reused | Read | Prompt tok/s | First token (s) | Decode tok/s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 811 | 0 | 811 | 795.6 | 1.034 | 94.3 |
| 1 | 4285 | 823 | 3462 | 2268.5 | 1.544 | 145.5 |
| 2 | 5818 | 4349 | 1469 | 1569.3 | 0.952 | 168.7 |
| 3 | 9251 | 5881 | 3370 | 2241.4 | 1.521 | 153.3 |
| 4 | 12010 | 9302 | 2708 | 2097.6 | 1.309 | 176.7 |
| 5 | 14881 | 12062 | 2819 | 2148.3 | 1.331 | 177.9 |

Per-request data: `results.json`. Engine log lines from the start: `engine-log-excerpt.txt` (when this run started the server).

## Correctness and limitations

Not measured: this is a speed suite. The conversation uses the model's own replies, so token counts differ a little between runs. Machine details come from the server, `nvidia-smi`/`rocm-smi` and the OS; background load and power limits are not recorded. Total time of the suite: 80 s.
