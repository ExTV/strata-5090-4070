"""Bench: 5 greedy thinking-off decodes (600 tok), fresh prompts of ~2K x2, ~16K, ~80K (prefill tok/s),
then a 2K follow-up on the 80K prompt (cache reuse). Prints one JSON line."""
import json, os, zlib, random, string, sys, time, urllib.request
B = os.environ.get("STRATA_URL", "http://127.0.0.1:8888")
M = json.load(urllib.request.urlopen(B + "/v1/models"))["data"][0]["id"]
def chat(msgs, max_tokens):
    body = {"model": M, "messages": msgs, "max_tokens": max_tokens, "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False}}
    t = time.time()
    r = json.load(urllib.request.urlopen(urllib.request.Request(B + "/v1/chat/completions", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}), timeout=3600))
    return r, time.time() - t
def doc(seed, words):
    rng = random.Random(seed)
    return " ".join("".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(3, 9))) for _ in range(words))
Q = ["Write a Python function that parses a CSV file and returns per-column statistics, with docstrings.",
     "Explain how a hash map handles collisions, with examples in C.",
     "Write a detailed essay on the history of the printing press.",
     "Implement a thread-safe LRU cache in Rust and explain the design.",
     "Describe the water cycle step by step for a high school class."]
dec = []
for q in Q:
    r, dt = chat([{"role": "user", "content": q}], 600); dec.append(round(r["usage"]["completion_tokens"] / dt))
print(json.dumps({"variant": sys.argv[1], "decode_after": sorted(dec), "median": sorted(dec)[2]}), flush=True)
