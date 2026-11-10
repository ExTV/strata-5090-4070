#!/usr/bin/env python3
"""Fresh long prompts with a needle: for each WORDS argument a prompt of that many random words (about 3.4 tokens
per word, a different seed per size so nothing is reused) with one sentence hidden a third of the way in, then a
short follow-up on the same chat.  Prints prompt tokens, prompt seconds, decode tok/s, ms per verify window and
whether the needle came back.

    tools/prompt_bench.py 23700 74000        -> about 80K and 250K tokens
"""
import json, os, random, string, sys, urllib.request
B = os.environ.get("STRATA_URL", "http://127.0.0.1:8888")
M = os.environ.get("MODEL", "qwen3.8-flash-next")
def chat(msgs, n):
    body = {"model": M, "messages": msgs, "max_tokens": n, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    r = json.load(urllib.request.urlopen(urllib.request.Request(B + "/v1/chat/completions", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}), timeout=3600))
    t = r["timings"]; w = t["predicted_n"] - t["draft_n_accepted"]
    return r["choices"][0]["message"]["content"], {"prompt_n": t["prompt_n"], "prompt_s": round(t["prompt_ms"] / 1000, 1),
            "tok": t["predicted_n"], "tps": round(t["predicted_per_second"], 1), "ms_win": round(t["predicted_ms"] / max(w, 1), 2)}
for i, words_n in enumerate(int(a) for a in sys.argv[1:]):
    rng = random.Random(100 + i)
    words = ["".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(3, 9))) for _ in range(words_n)]
    code = str(10000 + (100 + i) * 7); words.insert(words_n // 3, "The hidden code is %s." % code)
    m = [{"role": "user", "content": " ".join(words) + "\n\nWhat is the hidden code in the text above? Then write a short essay on the printing press."}]
    a, t = chat(m, 300); t["needle"] = code in a; print("fresh", t, flush=True)
    m += [{"role": "assistant", "content": a}, {"role": "user", "content": "Now explain how a hash map handles collisions, with C examples."}]
    a, t = chat(m, 400); print("follow", t, flush=True)
