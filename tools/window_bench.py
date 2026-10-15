#!/usr/bin/env python3
"""A/B gate for engine changes: ms per verify window on 7 short prompts (code/reasoning/prose, 600 tok, thinking off, temp 0) plus one ~20K-token
context prompt (300 tok). Window count = predicted_n - draft_n_accepted from the response's timings. One JSON line."""
import json, os, random, string, sys, time, urllib.request
B = os.environ.get("STRATA_URL", "http://127.0.0.1:8888"); TAG = sys.argv[1] if len(sys.argv) > 1 else "run"
M = json.load(urllib.request.urlopen(B + "/v1/models"))["data"][0]["id"]
def chat(msgs, n, **extra):
    body = {"model": M, "messages": msgs, "max_tokens": n, "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False}, **extra}
    r = json.load(urllib.request.urlopen(urllib.request.Request(B + "/v1/chat/completions", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}), timeout=3600))
    t = r["timings"]; w = t["predicted_n"] - t["draft_n_accepted"]
    return {"tok": t["predicted_n"], "win": w, "ms_win": round(t["predicted_ms"] / max(w, 1), 2),
            "acc": round(t["draft_n_accepted"] / max(t["draft_n"], 1), 3), "tps": round(t["predicted_per_second"], 1),
            "prompt_s": round(t["prompt_ms"] / 1000, 1)}
Q = [("code", "Write a Python function that parses a CSV file and returns per-column statistics, with docstrings."),
     ("code", "Implement a thread-safe LRU cache in Rust and explain the design."),
     ("code", "Write a bash script that rotates logs in /var/log/app, keeping 7 compressed copies, with comments."),
     ("reason", "A train leaves at 9:40 at 80 km/h, another at 10:10 at 120 km/h on the same track. When and where does the second catch the first? Show every step."),
     ("reason", "Explain how a hash map handles collisions, with examples in C."),
     ("prose", "Write a detailed essay on the history of the printing press."),
     ("prose", "Describe the water cycle step by step for a high school class.")]
for p in ["Say hi.", "Count to five."]: chat([{"role": "user", "content": p}], 16)   # warm
rows = []
for kind, q in Q:
    r = chat([{"role": "user", "content": q}], 600); r["kind"] = kind; rows.append(r)
rng = random.Random(7)
doc = " ".join("".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(3, 9))) for _ in range(15000))
r = chat([{"role": "user", "content": doc + "\n\nThe text above is random. Write a detailed essay on the history of the printing press."}], 300)
r["kind"] = "ctx20k"; rows.append(r)
med = lambda xs: sorted(xs)[len(xs) // 2]
out = {"variant": TAG, "ms_win_median7": med([r["ms_win"] for r in rows[:7]]),
       "ms_win": {k: round(sum(r["ms_win"] for r in rows if r["kind"] == k) / sum(1 for r in rows if r["kind"] == k), 2)
                  for k in ("code", "reason", "prose", "ctx20k")},
       "acc_mean7": round(sum(r["acc"] for r in rows[:7]) / 7, 3), "tps_median7": med([r["tps"] for r in rows[:7]]),
       "ctx20k": rows[7], "rows": rows}
print(json.dumps(out), flush=True)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.jsonl"), "a") as f: f.write(json.dumps(out) + "\n")
