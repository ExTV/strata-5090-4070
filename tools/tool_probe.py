#!/usr/bin/env python3
"""Agent-shaped tool-call probe: two turns, streamed, the shape a coding agent sends.  Turn 1 asks for two parallel
read_file calls with integer arguments; turn 2 feeds the results (a Jinja file that documents the call format) and
asks for an edit_file whose old and new strings contain a literal `<parameter=limit>..</parameter>` line, plus a
bash call with an integer timeout.  A sequence passes when both turns come back as parsed calls with the right
values.  Run it several times: the model's own misses (a call it never writes) are noise of 5-15 points per 15.

    tools/tool_probe.py [N=15] [TAG=agentic]      -> agentic-TAG.json, one line per sequence
    STRATA_URL (default http://127.0.0.1:8888), MODEL (qwen3.8-flash-next), EFFORT (sent as reasoning_effort when set)
"""
import json, os, sys, time, urllib.request
BASE = os.environ.get("STRATA_URL", "http://127.0.0.1:8888")
MODEL = os.environ.get("MODEL", "qwen3.8-flash-next")
EFFORT = os.environ.get("EFFORT")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 15
TAG = sys.argv[2] if len(sys.argv) > 2 else "agentic"


def fn(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props, "required": req}}}


TOOLS = [
    fn("read_file", "Read a file. Returns numbered lines.",
       {"path": {"type": "string"}, "offset": {"type": "integer", "description": "1-based first line"},
        "limit": {"type": "integer", "description": "max lines"}}, ["path"]),
    fn("edit_file", "Replace old_string with new_string exactly once.",
       {"path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}},
       ["path", "old_string", "new_string"]),
    fn("bash", "Run a shell command.",
       {"command": {"type": "string"}, "timeout": {"type": "integer", "description": "seconds"}}, ["command"]),
    fn("write_file", "Write a file.", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
]
FILE = ('{%- for m in messages %}\n{%- if m.role == "tool" %}\n<tool_response>\n{{ m.content }}\n</tool_response>\n'
        '{%- endif %}\n{%- endfor %}\n{#- example call format -#}\n<tool_call>\n<function=read_file>\n'
        '<parameter=path>README.md</parameter>\n<parameter=limit>40</parameter>\n</function>\n</tool_call>\n')
T1 = ("Read the first 20 lines of templates/chat.jinja and the first 10 lines of tests/test_template.py, both with "
      "the read_file tool, in parallel, before doing anything else.")
T2 = ("In templates/chat.jinja the example call uses limit 40; change that example line so the limit is 25 (keep the "
      "surrounding XML tags exactly as they are), using edit_file with the exact old and new text. Then run the tests "
      "with bash: `pytest -q tests/test_template.py` with a 120 second timeout. Do both calls now.")


def numbered(text, start=1):
    return "\n".join(f"{i + start:4d}| {l}" for i, l in enumerate(text.split("\n")))


def stream(messages, seed):
    body = {"model": MODEL, "stream": True, "max_tokens": 3000, "seed": seed, "tools": TOOLS, "tool_choice": "auto",
            "messages": messages}
    if EFFORT:
        body["reasoning_effort"] = EFFORT
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=600)
    calls, content, reasoning, finish = {}, "", "", None
    for line in r:
        line = line.decode().strip()
        if not line.startswith("data:") or line == "data: [DONE]":
            continue
        ch = json.loads(line[5:])["choices"][0]
        d = ch.get("delta", {})
        content += d.get("content") or ""
        reasoning += d.get("reasoning") or d.get("reasoning_content") or ""
        for tc in d.get("tool_calls") or []:
            s = calls.setdefault(tc.get("index", 0), {"id": None, "name": None, "args": ""})
            if tc.get("id"):
                s["id"] = tc["id"]
            f = tc.get("function") or {}
            if f.get("name"):
                s["name"] = f["name"]
            s["args"] += f.get("arguments") or ""
        if ch.get("finish_reason"):
            finish = ch["finish_reason"]
    parsed = []
    for idx, c in sorted(calls.items()):
        try:
            a, err = json.loads(c["args"]), None
        except Exception as e:
            a, err = None, f"{type(e).__name__}: {e}"[:80]
        parsed.append({"id": c["id"], "name": c["name"], "args": a, "raw": c["args"], "err": err})
    return {"finish": finish, "content": content, "reasoning": reasoning, "calls": parsed}


def check(i):
    issues = []
    r1 = stream([{"role": "user", "content": T1}], seed=i)
    names = [c["name"] for c in r1["calls"]]
    if len(r1["calls"]) < 2:
        issues.append(f"turn1 expected 2 read_file calls, got {names} finish={r1['finish']} "
                      f"content={len(r1['content'])} reasoning={len(r1['reasoning'])}")
    for c in r1["calls"]:
        if c["err"]:
            issues.append(f"turn1 unparseable {c['name']}: {c['err']} raw_tail={c['raw'][-50:]!r}")
        elif c["name"] not in [t["function"]["name"] for t in TOOLS]:
            issues.append(f"turn1 unknown tool {c['name']!r}")
        else:
            for k in ("offset", "limit"):
                if k in c["args"] and not isinstance(c["args"][k], int):
                    issues.append(f"turn1 {k} is {type(c['args'][k]).__name__} {c['args'][k]!r}, expected int")
    if issues:
        return issues
    asst = {"role": "assistant", "content": r1["content"] or None, "reasoning": r1["reasoning"] or None,
            "tool_calls": [{"id": c["id"] or f"call_{i}_{n}", "type": "function",
                            "function": {"name": c["name"], "arguments": c["raw"]}} for n, c in enumerate(r1["calls"])]}
    msgs = [{"role": "user", "content": T1}, asst]
    for c in asst["tool_calls"]:
        a = json.loads(c["function"]["arguments"])
        body = FILE if "jinja" in a.get("path", "") else "import jinja2\n\ndef test_render():\n    assert True\n"
        msgs.append({"role": "tool", "tool_call_id": c["id"], "content": numbered(body)})
    msgs.append({"role": "user", "content": T2})
    r2 = stream(msgs, seed=1000 + i)
    names2 = [c["name"] for c in r2["calls"]]
    if "edit_file" not in names2 or "bash" not in names2:
        issues.append(f"turn2 expected edit_file+bash, got {names2} finish={r2['finish']} "
                      f"content={r2['content'][:120]!r} reasoning_len={len(r2['reasoning'])}")
    for c in r2["calls"]:
        if c["err"]:
            issues.append(f"turn2 unparseable {c['name']}: {c['err']} raw_tail={c['raw'][-60:]!r}")
            continue
        if c["name"] == "edit_file":
            o, n = c["args"].get("old_string", ""), c["args"].get("new_string", "")
            if o not in FILE:
                issues.append(f"turn2 old_string not in file: {o!r}")
            if "<parameter=limit>25</parameter>" not in n:
                issues.append(f"turn2 new_string wrong: {n!r}")
        if c["name"] == "bash":
            t = c["args"].get("timeout")
            if t is not None and not isinstance(t, int):
                issues.append(f"turn2 timeout is {type(t).__name__} {t!r}")
            if "pytest" not in c["args"].get("command", ""):
                issues.append(f"turn2 bash command {c['args'].get('command')!r}")
    return issues


fails, log = 0, []
for i in range(N):
    t0 = time.time()
    try:
        issues = check(i)
    except Exception as e:
        issues = [f"transport: {type(e).__name__}: {e}"[:200]]
    fails += bool(issues)
    log.append({"i": i, "issues": issues})
    print(f"[{TAG}] {i:02d} {time.time() - t0:.1f}s " + ("ok" if not issues else "FAIL " + " || ".join(issues)), flush=True)
print(f"[{TAG}] SUMMARY failed_sequences={fails}/{N}")
json.dump(log, open(f"agentic-{TAG}.json", "w"), indent=1)
