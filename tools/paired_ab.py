"""Paired A/B of per-request settings on one boot: arms per prompt with a settle request first (prompt cached, expert tier refilled) and the arm order rotated
per prompt. usage: paired_ab.py <temp> <arm-json> ...   e.g. '{"strata_tune":{"spec_min_p":0.9}}'"""
import json, os, random, string, sys, urllib.request
B = os.environ.get("STRATA_URL", "http://127.0.0.1:8888"); M = json.load(urllib.request.urlopen(B + "/v1/models"))["data"][0]["id"]
TEMP = float(sys.argv[1]); ARMS = [json.loads(a) for a in sys.argv[2:]]
Q = ["Write a Python function that parses a CSV file and returns per-column statistics, with docstrings.",
     "Implement a thread-safe LRU cache in Rust and explain the design.",
     "Write a bash script that rotates logs in /var/log/app, keeping 7 compressed copies, with comments.",
     "A train leaves at 9:40 at 80 km/h, another at 10:10 at 120 km/h on the same track. When and where does the second catch the first? Show every step.",
     "Explain how a hash map handles collisions, with examples in C.",
     "Write a detailed essay on the history of the printing press.",
     "Describe the water cycle step by step for a high school class."]
rng = random.Random(7)
doc = " ".join("".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(3, 9))) for _ in range(15000))
Q.append(doc + "\n\nThe text above is random. Write a detailed essay on the history of the printing press.")
def chat(q, extra, n):
    body = {"model": M, "messages": [{"role": "user", "content": q}], "max_tokens": n, "temperature": TEMP,
            "chat_template_kwargs": {"enable_thinking": False}, **extra}
    t = json.load(urllib.request.urlopen(urllib.request.Request(B + "/v1/chat/completions", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}), timeout=3600))["timings"]
    return t["predicted_per_second"], t["predicted_n"] / max(t["predicted_n"] - t["draft_n_accepted"], 1)
res = [[] for _ in ARMS]
for i, q in enumerate(Q):
    chat(q, {}, 48)                                   # settle: prompt into the cache, tier refilled
    for k in range(len(ARMS)):
        j = (i + k) % len(ARMS); res[j].append(chat(q, ARMS[j], 600 if i < 7 else 300))
for j, a in enumerate(ARMS):
    tps = [r[0] for r in res[j]]; b = [r[0] for r in res[0]]
    print(f"temp {TEMP} {json.dumps(a):45s} median7 {sorted(tps[:7])[3]:5.0f} ctx20k {tps[7]:5.0f} | vs arm0 wins {sum(x > y for x, y in zip(tps, b))}/8 "
          f"ratio {sum(x / y for x, y in zip(tps, b)) / 8:.3f} | tok/win {sum(r[1] for r in res[j]) / 8:.2f}")
