"""Correctness: a needle in a ~40K prompt, then two follow-up turns (exercise the stage->main copy), greedy."""
import json, random, string, sys, time, urllib.request
B = "http://127.0.0.1:8888"
M = json.load(urllib.request.urlopen(B + "/v1/models"))["data"][0]["id"]
def chat(msgs, n):
    body = {"model": M, "messages": msgs, "max_tokens": n, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    t = time.time()
    r = json.load(urllib.request.urlopen(urllib.request.Request(B + "/v1/chat/completions", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}), timeout=3600))
    return r["choices"][0]["message"]["content"], time.time() - t, r["usage"]["prompt_tokens"]
rng = random.Random(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
words = ["".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(3, 9))) for _ in range(12000)]
words.insert(9000, "The secret code for the blue door is 4817.")
words.insert(3000, "The secret code for the red door is 2290.")
msgs = [{"role": "user", "content": " ".join(words) + "\n\nWhat is the secret code for the blue door? Answer with the number only."}]
a, dt, pt = chat(msgs, 16); print(f"T1 {pt} tok {dt:.1f}s -> {a!r}")
msgs += [{"role": "assistant", "content": a}, {"role": "user", "content": "And the red door? Number only."}]
a, dt, pt = chat(msgs, 16); print(f"T2 {pt} tok {dt:.1f}s -> {a!r}")
msgs += [{"role": "assistant", "content": a}, {"role": "user", "content": "Write the planets of the solar system in order, comma separated."}]
a, dt, pt = chat(msgs, 60); print(f"T3 {pt} tok {dt:.1f}s -> {a!r}")
msgs += [{"role": "assistant", "content": a}, {"role": "user", "content": "Add both door codes together. Number only."}]
a, dt, pt = chat(msgs, 16); print(f"T4 {pt} tok {dt:.1f}s -> {a!r}")
more = ["".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(3, 9))) for _ in range(6000)]
more.insert(2500, "The secret code for the green door is 5531.")
msgs += [{"role": "assistant", "content": a}, {"role": "user", "content": " ".join(more) + "\n\nList the blue, red and green door codes, comma separated."}]
a, dt, pt = chat(msgs, 24); print(f"T5 {pt} tok {dt:.1f}s -> {a!r}")
