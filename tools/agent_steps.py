#!/usr/bin/env python3
"""Agent-step latency: a ~13K-token first message, then follow-ups of ~1.5K / 2.4K / 5.4K / 0.5K fresh tokens (tool
results), 60 tokens answered each. Per step: fresh tokens, prompt seconds, total seconds, GB read from the SSD
(NVME=nvme0n1 names the block device; the default is nvme1n1). One JSON line. Usage: agent_steps.py TAG [SEED]"""
import json, os, random, string, sys, time, urllib.request
B = os.environ.get("STRATA_URL", "http://127.0.0.1:8888"); TAG = sys.argv[1] if len(sys.argv) > 1 else "run"
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 500; DEV = os.environ.get("NVME", "nvme1n1")
M = json.load(urllib.request.urlopen(B + "/v1/models"))["data"][0]["id"]
def nvme_gb():
    try: return int(open(f"/sys/block/{DEV}/stat").read().split()[2]) * 512 / 1e9
    except OSError: return 0.0
def doc(seed, words):
    rng = random.Random(seed)
    return " ".join("".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(3, 9))) for _ in range(words))
msgs = [{"role": "user", "content": "Project notes:\n" + doc(SEED, 3800) + "\n\nSummarize in one sentence."}]
rows = []
for i, words in enumerate([0, 450, 700, 1600, 150]):
    if i > 0:
        msgs.append({"role": "user", "content": "Tool result:\n" + doc(SEED + i, words) + "\n\nOne sentence: what next?"})
    body = {"model": M, "messages": msgs, "max_tokens": 60, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    r0, t0 = nvme_gb(), time.time()
    r = json.load(urllib.request.urlopen(urllib.request.Request(B + "/v1/chat/completions", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}), timeout=3600))
    dt = time.time() - t0; t = r["timings"]
    rows.append({"step": i, "fresh": t["prompt_n"] - t["cache_n"], "prompt_s": round(t["prompt_ms"] / 1000, 2),
                 "total_s": round(dt, 2), "nvme_gb": round(nvme_gb() - r0, 1)})
    msgs.append({"role": "assistant", "content": r["choices"][0]["message"]["content"]})
print(TAG, json.dumps(rows))
