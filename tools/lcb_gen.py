#!/usr/bin/env python3
"""LiveCodeBench code generation against an OpenAI-compatible endpoint, with the harness's generic chat prompt.
    tools/lcb_gen.py OUT.jsonl --data test6.jsonl [--url URL] [--model NAME] [--think] [--temperature T] [--limit N]
        [--workers N] [--openrouter]   (key from env LCB_AUTH)
Resumable: questions already in OUT.jsonl are skipped."""
import argparse, json, os, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
SYS = ("You are an expert Python programmer. You will be given a question (problem specification) and will generate a "
       "correct Python program that matches the specification and passes all tests.")
WITH = "You will use the following starter code to write the solution to the problem and enclose your code within delimiters."
WITHOUT = ("Read the inputs from stdin solve the problem and write the answer to stdout (do not directly test on the "
           "sample inputs). Enclose your code within delimiters as follows. Ensure that when the python program runs, "
           "it reads the inputs, runs the algorithm and writes output to STDOUT.")
def prompt(q):
    p = f"### Question:\n{q['question_content']}\n\n"
    if q["starter_code"]:
        p += f"### Format: {WITH}\n```python\n{q['starter_code']}\n```\n\n"
    else:
        p += f"### Format: {WITHOUT}\n```python\n# YOUR CODE HERE\n```\n\n"
    return p + "### Answer: (use the provided format with backticks)\n\n"
a = argparse.ArgumentParser()
a.add_argument("out"); a.add_argument("--url", default="http://127.0.0.1:8888/v1")
a.add_argument("--model", default="qwen3.8-flash-next"); a.add_argument("--think", action="store_true")
a.add_argument("--temperature", type=float, default=0.0); a.add_argument("--max-tokens", type=int, default=8192)
a.add_argument("--limit", type=int, default=0); a.add_argument("--workers", type=int, default=1)
a.add_argument("--openrouter", action="store_true", help="send OpenRouter's reasoning switch instead of chat_template_kwargs"); a.add_argument("--data", required=True, help="a jsonl of livecodebench/code_generation_lite, e.g. test6.jsonl")
a = a.parse_args()
done = {json.loads(l)["question_id"] for l in open(a.out)} if os.path.exists(a.out) else set()
qs = [json.loads(l) for l in open(a.data)]
if a.limit: qs = qs[:a.limit]
out = open(a.out, "a"); t00 = time.time(); lock = threading.Lock(); stat = {"n": 0, "tok": 0}
def one(q):
    body = {"model": a.model, "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": prompt(q)}],
            "temperature": a.temperature, "max_tokens": a.max_tokens}
    if a.openrouter: body["reasoning"] = {"enabled": a.think}
    else: body["chat_template_kwargs"] = {"enable_thinking": a.think}
    if a.temperature > 0: body["top_p"] = 0.95
    req = urllib.request.Request(a.url + "/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + os.environ.get("LCB_AUTH", "none")})
    t0 = time.time()
    for attempt in range(4):
        try:
            r = json.load(urllib.request.urlopen(req, timeout=3600))
            m, u = r["choices"][0]["message"], r.get("usage", {})
            break
        except Exception as e:
            print("retry", q["question_id"], repr(e)[:200], flush=True); time.sleep(10)
    else:
        print("FAILED", q["question_id"], flush=True); return
    with lock:
        stat["n"] += 1; stat["tok"] += u.get("completion_tokens", 0)
        out.write(json.dumps({"question_id": q["question_id"], "difficulty": q["difficulty"], "platform": q["platform"],
                              "content": m.get("content") or "", "finish": r["choices"][0].get("finish_reason"),
                              "completion_tokens": u.get("completion_tokens"),
                              "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                              "provider": r.get("provider"), "seconds": round(time.time() - t0, 2)}) + "\n"); out.flush()
        if stat["n"] % 25 == 0: print(f"{stat['n']} answered, {time.time()-t00:.0f} s, {stat['tok']} tokens", flush=True)
todo = [q for q in qs if q["question_id"] not in done]
with ThreadPoolExecutor(a.workers) as ex: list(ex.map(one, todo))
print(f"answered {stat['n']} of {len(todo)} in {time.time()-t00:.0f} s, {stat['tok']} completion tokens")
