#!/usr/bin/env python3
"""Grades tools/lcb_gen.py output with LiveCodeBench's own checker (6 s per test).  It runs model-written code, so run
it in a container without network: the harness checkout at /lcb, the problem file at /data/test6.jsonl.

    printf 'FROM python:3.11-slim\nRUN pip install --no-cache-dir numpy tqdm\n' | docker build -t lcb-grader -
    docker run --rm --network none --memory 12g --pids-limit 512 -v $PWD/LiveCodeBench:/lcb:ro -v $PWD/data:/data:ro \
        -v $PWD/out:/out -v $PWD/tools/lcb_grade.py:/grade.py:ro lcb-grader python /grade.py /out/RUN.jsonl
"""
import base64, json, pickle, sys, zlib
sys.path.insert(0, "/lcb")
from lcb_runner.evaluation.compute_code_generation_metrics import codegen_metrics
def extract(o):
    lines = o.split("\n"); idx = [i for i, l in enumerate(lines) if "```" in l]
    return "" if len(idx) < 2 else "\n".join(lines[idx[-2] + 1:idx[-1]])
qs = {}
for l in open("/data/test6.jsonl"):
    q = json.loads(l)
    pub = json.loads(q["public_test_cases"])
    try: prv = json.loads(q["private_test_cases"])
    except Exception: prv = json.loads(pickle.loads(zlib.decompress(base64.b64decode(q["private_test_cases"].encode()))))
    t = pub + prv
    qs[q["question_id"]] = {"input_output": json.dumps({"inputs": [x["input"] for x in t], "outputs": [x["output"] for x in t],
                                                        "fn_name": json.loads(q["metadata"]).get("func_name")})}
for path in sys.argv[1:]:
    rows = [json.loads(l) for l in open(path)]
    samples = [qs[r["question_id"]] for r in rows]; gens = [[extract(r["content"])] for r in rows]
    metrics, results, _ = codegen_metrics(samples, gens, k_list=[1], num_process_evaluate=12, timeout=6)
    ok = [all(x is True or x == 1 for x in results[i][0]) for i in range(len(rows))]
    by = {}
    for r, o in zip(rows, ok): by.setdefault(r["difficulty"], []).append(o)
    json.dump({r["question_id"]: o for r, o in zip(rows, ok)}, open(path + ".graded.json", "w"))
    print(path, f"pass@1 {sum(ok)}/{len(ok)} = {sum(ok)/len(ok)*100:.1f}%", {k: f"{sum(v)}/{len(v)}" for k, v in sorted(by.items())},
          "empty code:", sum(1 for g in gens if not g[0]), "length-cut:", sum(1 for r in rows if r["finish"] == "length"), flush=True)
