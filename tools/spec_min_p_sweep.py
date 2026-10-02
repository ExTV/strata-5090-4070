"""spec-min-p sweep without a restart: the same 5 prompts (600 tokens, temperature 0.6 like real use, fixed seed)
at strata_tune.spec_min_p 0.3 / 0.5 / 0.7, interleaved so drift hits every arm alike. Prints one JSON line."""
import json, os, sys, time, urllib.request
B = os.environ.get("STRATA_URL", "http://127.0.0.1:8888")
M = json.load(urllib.request.urlopen(B + "/v1/models"))["data"][0]["id"]
Q = ["Write a Python function that parses a CSV file and returns per-column statistics, with docstrings.",
     "Explain how a hash map handles collisions, with examples in C.",
     "Write a detailed essay on the history of the printing press.",
     "Implement a thread-safe LRU cache in Rust and explain the design.",
     "Describe the water cycle step by step for a high school class."]
def chat(q, minp):
    body = {"model": M, "messages": [{"role": "user", "content": q}], "max_tokens": 600, "temperature": 0.6,
            "top_p": 0.95, "top_k": 20, "seed": 11, "chat_template_kwargs": {"enable_thinking": False},
            "strata_tune": {"spec_min_p": minp}}
    t = time.time()
    r = json.load(urllib.request.urlopen(urllib.request.Request(B + "/v1/chat/completions", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}), timeout=3600))
    return r["usage"]["completion_tokens"] / (time.time() - t)
chat(Q[0], 0.5)   # warm
res = {"variant": sys.argv[1] if len(sys.argv) > 1 else "minp"}
for minp in (0.3, 0.5, 0.7): res[str(minp)] = []
for q in Q:
    for minp in (0.3, 0.5, 0.7): res[str(minp)].append(round(chat(q, minp)))
for minp in (0.3, 0.5, 0.7): res[str(minp) + "_median"] = sorted(res[str(minp)])[2]
print(json.dumps(res), flush=True)
