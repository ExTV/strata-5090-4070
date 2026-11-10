# Tools

All talk to `127.0.0.1:8888` unless `STRATA_URL` is set.

| Script | Measures |
| --- | --- |
| `tools/bench.py NAME` | 5 decodes, 2K / 16K / 80K fresh prompts, a follow-up (one JSON line) |
| `tools/depth_bench.py` | the depth tables in [benchmarks.md](benchmarks.md) |
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
| `tools/engine_logprobs.py capture\|ids\|run\|ppl\|vs-llama\|vs` | teacher-forced log-probabilities straight from the engine (the server stopped): perplexity, top-token agreement and KL against a `llama-perplexity` logits file or another run ([quality.md](quality.md)) |
| `tools/lcb_gen.py OUT.jsonl --data test6.jsonl` | LiveCodeBench code generation with the harness's prompt against any OpenAI-compatible endpoint (`LCB_AUTH`, `--think`, `--workers`, `--openrouter`) |
| `tools/lcb_grade.py` | grades it with the harness's checker; run it in a container without network (command in the file) |
| `tools/make_comparison_chart.py` | redraws `docs/comparison-light.svg` and `-dark.svg` (the README image) from the numbers in the script |
