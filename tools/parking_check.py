"""Two conversations alternating (A ~30K with a needle, B ~15K with another), 4 rounds; each turn must answer its own
needle and, after the first read, reuse its history instead of re-reading it."""
import json, os, random, string, time, urllib.request
B = os.environ.get("STRATA_URL", "http://127.0.0.1:8888")
M = json.load(urllib.request.urlopen(B + "/v1/models"))["data"][0]["id"]
def chat(msgs, n):
    body = {"model": M, "messages": msgs, "max_tokens": n, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    t = time.time()
    r = json.load(urllib.request.urlopen(urllib.request.Request(B + "/v1/chat/completions", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}), timeout=3600))
    return r["choices"][0]["message"]["content"], time.time() - t, r["usage"]["prompt_tokens"]
def doc(seed, n, fact, at):
    rng = random.Random(seed)
    w = ["".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(3, 9))) for _ in range(n)]
    w.insert(at, fact); return " ".join(w)
conv = {"A": [{"role": "user", "content": doc(1, 9000, "The vault code is 3141.", 4000) + "\n\nWhat is the vault code? Number only."}],
        "B": [{"role": "user", "content": doc(2, 4500, "The cat is named Pickle.", 2000) + "\n\nWhat is the cat named? One word."}]}
follow = {"A": ["Repeat the vault code. Number only.", "Vault code plus one? Number only.", "Vault code again? Number only."],
          "B": ["Repeat the cat's name. One word.", "Spell the cat's name backwards. One word.", "Cat's name again? One word."]}
for rnd in range(4):
    for k in "AB":
        if rnd > 0: conv[k] += [{"role": "user", "content": follow[k][rnd - 1]}]
        a, dt, pt = chat(conv[k], 12)
        print(f"round {rnd} {k}: {pt} tok in {dt:.1f}s -> {a!r}", flush=True)
        conv[k] += [{"role": "assistant", "content": a}]
