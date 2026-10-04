"""usage: step_times.py NAME TEXTFILE.  Tool-loop shaped reads on real text: a ~12K-token first message cut from
TEXTFILE, then follow-ups of ~1.3K, ~2.5K and ~5K tokens (3 each), 2 output tokens.  Prints one JSON line with the
seconds per step.  Use real text (web pages, logs, code): words drawn from a small vocabulary route to few experts
and make the batched prompt path look about three times cheaper than it is."""
import json, os, sys, time, urllib.request
B = os.environ.get("STRATA_URL", "http://127.0.0.1:8888")
M = json.load(urllib.request.urlopen(B + "/v1/models"))["data"][0]["id"]
DOC = open(sys.argv[2], encoding="utf-8", errors="replace").read()
POS = [0]
def text(n):                                    # about n tokens: ~3.3 characters a token on web text
    a = POS[0]; POS[0] += int(n * 3.3)
    if POS[0] > len(DOC): sys.exit("the text file is too short: about 150,000 characters are needed")
    return DOC[a:POS[0]]
def chat(msgs):
    body = {"model": M, "messages": msgs, "max_tokens": 2, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    t = time.time()
    r = json.load(urllib.request.urlopen(urllib.request.Request(B + "/v1/chat/completions", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}), timeout=600))
    return r, time.time() - t
msgs = [{"role": "user", "content": "Notes:\n" + text(12000) + "\nReply OK."}]
r, dt = chat(msgs); last = r["usage"]["prompt_tokens"] + r["usage"]["completion_tokens"]
msgs.append({"role": "assistant", "content": r["choices"][0]["message"]["content"] or "OK"})
res = {"variant": sys.argv[1], "base": f"{last} tok {dt:.1f}s"}
for n in (1300, 2500, 5000):
    ts = []
    for _ in range(3):
        msgs.append({"role": "user", "content": text(n) + "\nReply OK."})
        r, dt = chat(msgs); new = r["usage"]["prompt_tokens"] - last
        last = r["usage"]["prompt_tokens"] + r["usage"]["completion_tokens"]
        msgs.append({"role": "assistant", "content": r["choices"][0]["message"]["content"] or "OK"})
        ts.append(round(dt, 2))
    res[f"step_{new}"] = ts
print(json.dumps(res), flush=True)
