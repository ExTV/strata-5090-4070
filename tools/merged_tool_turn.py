"""A client that sends every tool call of a turn in ONE assistant message, followed by all the results (some chat
apps keep one assistant message per user turn).  Runs a 4-step tool loop with ~3K-token results.  With patch 10
every step reuses the whole conversation (check "reused" in the engine log); with OLD_IDS=1 the call ids are
rewritten to plain random ones, the server leaves the merged layout alone, and every step re-reads the turn."""
import json, os, random, string, urllib.request, uuid
B = os.environ.get("STRATA_URL", "http://127.0.0.1:8888")
M = json.load(urllib.request.urlopen(B + "/v1/models"))["data"][0]["id"]
TOOLS = [{"type": "function", "function": {"name": "fetch_page", "description": "Fetch one page of the report by number.",
          "parameters": {"type": "object", "properties": {"page": {"type": "integer"}}, "required": ["page"]}}}]
def page(n):
    rng = random.Random(n)
    return f"PAGE {n}. " + " ".join("".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(3, 9))) for _ in range(900)) + \
           f"\nThe code on page {n} is {1000 + 37 * n}." + (" Continue with the next page." if n < 4 else " This was the last page.")
def chat(msgs):
    body = {"model": M, "messages": msgs, "tools": TOOLS, "max_tokens": 400, "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False}}
    return json.load(urllib.request.urlopen(urllib.request.Request(B + "/v1/chat/completions", data=json.dumps(body).encode(),
                     headers={"Content-Type": "application/json"}), timeout=600))
user = {"role": "user", "content": "The report has 4 pages. Fetch page 1 with the tool, read it, then fetch the next page, "
        "one page per step, never two at once. After page 4, list the four codes."}
calls, results = [], []
for step in range(6):
    msgs = [user] + ([{"role": "assistant", "content": "", "tool_calls": calls}] + results if calls else [])
    r = chat(msgs); m = r["choices"][0]["message"]
    new = m.get("tool_calls") or []
    print(f"step {step}: prompt {r['usage']['prompt_tokens']} tok, ids {[c['id'] for c in new]}, content {(m.get('content') or '')[:90]!r}")
    if not new: break
    if os.environ.get("OLD_IDS"):
        for c in new: c["id"] = "call_" + uuid.uuid4().hex[:24]
    calls += new
    results += [{"role": "tool", "tool_call_id": c["id"], "content": page(json.loads(c["function"]["arguments"])["page"])} for c in new]
