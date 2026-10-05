"""Depth table: for each target depth, a fresh prompt of real text (code + docs) sized with the server's own token
counter, then a 256-token answer; streamed, so prefill = prompt tokens / time to first token and decode = answer
tokens / the rest.  Greedy, thinking off.  One JSON line per depth."""
import glob, json, os, sys, time, urllib.request, uuid

B = os.environ.get("STRATA_URL", "http://127.0.0.1:8888")
M = json.load(urllib.request.urlopen(B + "/v1/models"))["data"][0]["id"]
DEPTHS = [int(x) for x in (sys.argv[1:] or "2000 32000 62000 92000 122000 152000 182000 212000 242000 260000".split())]
ROOT = os.environ.get("STRATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "strata"))  # corpus: Strata's source
files = sorted(glob.glob(f"{ROOT}/docs/*.md")) + sorted(glob.glob(f"{ROOT}/src/**/*.cpp", recursive=True)) + \
        sorted(glob.glob(f"{ROOT}/src/**/*.cu", recursive=True)) + sorted(glob.glob(f"{ROOT}/serve/*.py"))
CORPUS = "".join(f"\n\n===== {os.path.relpath(f, ROOT)} =====\n" + open(f, errors="replace").read() for f in files)
ASK = "\n\nNow write a detailed explanation, about 400 words, of what the text above is and how its parts fit together."

def post(path, body):
    return urllib.request.urlopen(urllib.request.Request(B + path, data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json"}), timeout=7200)

def count(text):
    r = json.load(post("/v1/messages/count_tokens", {"model": M, "messages": [{"role": "user", "content": text}]}))
    return r["input_tokens"]

ratio = len(CORPUS[:200000]) / count(CORPUS[:200000])        # characters per token for this corpus
for d in DEPTHS:
    tag = f"[run {uuid.uuid4().hex[:12]}]\n"                 # a unique first line: no prefix-cache reuse
    n = int(d * ratio)
    text = tag + (CORPUS * (1 + n // len(CORPUS)))[:n] + ASK
    for _ in range(3):                                        # trim to the target with the real count
        c = count(text)
        n = int(n - (c - d) * ratio)
        text = tag + (CORPUS * (1 + n // len(CORPUS)))[:n] + ASK
    body = {"model": M, "messages": [{"role": "user", "content": text}], "max_tokens": 256, "temperature": 0,
            "stream": True, "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False}}
    t0 = time.time(); t1 = None; usage = None
    for raw in post("/v1/chat/completions", body):
        line = raw.decode().strip()
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        ev = json.loads(line[6:])
        if ev.get("usage"):
            usage = ev["usage"]
        if t1 is None and any((ch.get("delta") or {}).get("content") for ch in ev.get("choices", [])):
            t1 = time.time()
    t2 = time.time()
    pt, ct = usage["prompt_tokens"], usage["completion_tokens"]
    print(json.dumps({"depth": d, "prompt_tokens": pt, "ttft_s": round(t1 - t0, 1), "prefill_tps": round(pt / (t1 - t0)),
                      "gen_tokens": ct, "decode_tps": round((ct - 1) / (t2 - t1), 1)}), flush=True)
