#!/usr/bin/env python3
"""One conversation grown turn by turn to the context limit, the shape of a long agent session: every turn adds
15,000 characters of Strata's own source (about 4.5K tokens) and asks for a one-sentence summary.  Prints wall
seconds per turn, decode tok/s and the box's MemAvailable; the last line is the summary.  Fresh-prompt tests miss
what this one finds: memory that only runs out as a chat grows.  Watch /proc/vmstat pswpout around it for swap.

    tools/grow_chat.py [LIMIT=252000] [SRC_GLOB=strata/src/*/*.cpp]
"""
import glob, json, os, sys, time, urllib.request
B = os.environ.get("STRATA_URL", "http://127.0.0.1:8888")
M = os.environ.get("MODEL", "qwen3.8-flash-next")
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 252000
GLOB = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "strata", "src", "*", "*.cpp")
src = "".join(open(f, errors="ignore").read() for f in sorted(glob.glob(GLOB)))
assert src, "no source files under " + GLOB
m, pos, rows = [], 0, []
for turn in range(1, 200):
    m.append({"role": "user", "content": "Part %d of the source:\n\n%s\n\nSummarize this part in one sentence." % (turn, src[pos:pos + 15000])}); pos += 15000
    body = {"model": M, "messages": m, "max_tokens": 80, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    t0 = time.time()
    r = json.load(urllib.request.urlopen(urllib.request.Request(B + "/v1/chat/completions", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}), timeout=3600))
    dt = time.time() - t0; u = r["usage"]["prompt_tokens"]; t = r["timings"]
    m.append({"role": "assistant", "content": r["choices"][0]["message"]["content"]})
    avail = int(open("/proc/meminfo").read().split("MemAvailable:")[1].split()[0]) // 1024
    rows.append((u, dt, t["predicted_per_second"], avail))
    if turn % 8 == 0 or u > LIMIT:
        print("turn %d ctx %d wall %.1fs decode %.0f tok/s avail %d MiB" % (turn, u, dt, t["predicted_per_second"], avail), flush=True)
    if u > LIMIT:
        break
print("turns %d; wall max %.1f s, median %.1f s; decode mean %.0f tok/s; min avail %d MiB" % (len(rows), max(r[1] for r in rows),
      sorted(r[1] for r in rows)[len(rows) // 2], sum(r[2] for r in rows) / len(rows), min(r[3] for r in rows)))
