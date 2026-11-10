#!/usr/bin/env python3
"""Teacher-forced log-probabilities straight from the engine, to compare this build with another engine on the same
tokens.  The engine is started exactly as the running server started it (command line and environment copied from
the live process), with only the context size and the read path changed so that every token goes through the decode
windows, where STRATA_LOGPOS writes one line per position.  Stop the server before `run`: two engines do not fit.

    capture [PID] ENGINE.json        copy the running engine's command line and CUDA/STRATA/MALLOC environment
    ids TEXT NBYTES TOKENIZER_DIR STRATA_DIR IDS.json
                                     tokenize the first NBYTES of TEXT (no special tokens)
    run ENGINE.json OUT.tsv --logits FILE            the chunks of a `llama-perplexity --kl-divergence-base` file
    run ENGINE.json OUT.tsv --ids IDS.json [--context 4096 --stride 2048]
                                     fixed windows, each from empty state (ninfer-perplexity's protocol)
        run options: --no-cvec (drop the control vector), --kv TYPE, --unset A,B (environment switches to remove)
    ppl OUT.tsv NTOKENS [--context 4096 --stride 2048]     perplexity of a windows run
    vs-llama FILE OUT.tsv            perplexity of both, top-token agreement and KL(llama.cpp || Strata) over
                                     llama.cpp's 64 most likely tokens, on llama-perplexity's scored positions
    vs REF.tsv RUN.tsv [--context 512]                    the same between two chunk runs of this engine

OUT.tsv rows (the engine's format): position, target id, logp(target), argmax id, logp(argmax), argmax==target,
two more columns, then the 256 most likely tokens as id:logp (natural log).  numpy is needed for vs-llama and vs.
"""
import argparse, json, math, os, pathlib, struct, subprocess, sys, time

CVEC = {"--control-vector-scaled": 1, "--control-vector-layer-range": 2, "--cvec-mode": 1, "--cvec-dir": 1}
REPLACED = {"--max-context": 1, "--short-read": 1, "--prefill": 1, "--expert-profile-save": 1, "--prompt-cache": 1}


def cmd_capture(a):
    pid = a.pid or subprocess.run(["pgrep", "-f", "strata --serve"], capture_output=True, text=True).stdout.split()[0]
    argv = [x.decode() for x in pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if x]
    env = dict(kv.split("=", 1) for kv in pathlib.Path(f"/proc/{pid}/environ").read_bytes().decode().split("\0")
               if kv.startswith(("CUDA", "STRATA", "MALLOC", "LD_LIBRARY_PATH")))
    json.dump({"argv": argv, "env": env, "cwd": os.readlink(f"/proc/{pid}/cwd")}, open(a.out, "w"), indent=1)
    print(f"pid {pid}: {len(argv)} arguments, {len(env)} environment switches -> {a.out}")


def cmd_ids(a):
    sys.path.insert(0, str(pathlib.Path(a.strata) / "tools"))
    import strata_tokenizer as ST
    tp = pathlib.Path(a.tokenizer)
    vocab = json.loads((tp / "vocab.json").read_text(encoding="utf-8"))
    toks = [None] * len(vocab)
    for t, i in vocab.items():
        toks[i] = t
    tok = ST.Tokenizer(toks, (tp / "merges.txt").read_text(encoding="utf-8").split("\n"),
                       json.loads((tp / "token_type.json").read_text()))
    ids = tok.encode(open(a.text, "rb").read()[:a.nbytes].decode("utf-8", errors="ignore"))
    json.dump(ids, open(a.out, "w"))
    print(f"{len(ids)} tokens ({len(ids) - 1} targets) -> {a.out}")


def read_logits_header(path):
    f = open(path, "rb")
    if f.read(8) != b"_logits_":
        sys.exit(f"{path}: not a llama-perplexity logits file")
    n_ctx, n_vocab, n_chunk = struct.unpack("<iii", f.read(12))
    toks = struct.unpack(f"<{n_ctx * n_chunk}i", f.read(4 * n_ctx * n_chunk))
    return f, n_ctx, n_vocab, n_chunk, toks


def windows(n, ctx, stride):
    """(begin, first target, end) of every window: each token after the first is a target exactly once."""
    out, s = [(0, 1, min(ctx, n))], ctx
    while s < n:
        out.append((s - (ctx - stride), s, min(s + stride, n)))
        s += stride
    return out


def cmd_run(a):
    eng = json.load(open(a.engine))
    if a.logits:
        _, n_ctx, _, n_chunk, toks = read_logits_header(a.logits)
        reqs, ctx = [toks[c * n_ctx:(c + 1) * n_ctx] for c in range(n_chunk)], n_ctx
    else:
        ids = json.load(open(a.ids))
        reqs, ctx = [ids[b:e] for b, _, e in windows(len(ids), a.context, a.stride)], a.context
    drop = dict(REPLACED)
    if a.no_cvec:
        drop.update(CVEC)
    argv, i = [], 0
    while i < len(eng["argv"]):
        x = eng["argv"][i]
        if x in drop:
            i += 1 + drop[x]
        elif x == "--vision":
            i += 1
        else:
            argv.append(x)
            i += 1
    if a.kv:
        argv[argv.index("--kv") + 1] = a.kv
    argv += ["--max-context", str(ctx + 512), "--short-read", str(ctx + 64), "--prefill", "512", "--prompt-cache", "0"]
    env = dict(os.environ, **eng["env"])
    for k in (a.unset or "").split(","):
        env.pop(k, None)
    out = pathlib.Path(a.out).resolve()
    if out.exists():
        out.unlink()
    env["STRATA_LOGPOS"], env["STRATA_LOGPOS_TOPK"] = str(out), "256"
    print("engine:", " ".join(argv), flush=True)
    p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=open(str(out) + ".stderr.txt", "w"),
                         text=True, cwd=eng["cwd"], env=env, bufsize=1)
    t0 = time.time()
    for line in p.stdout:
        if line.startswith("READY"):
            break
    else:
        sys.exit(f"the engine ended before READY (exit {p.wait()}); see {out}.stderr.txt")
    print(f"READY after {time.time() - t0:.0f} s", flush=True)
    t0 = time.time()
    for n, r in enumerate(reqs):
        p.stdin.write("GEN 1 " + ",".join(map(str, r)) + "\n")
        p.stdin.flush()
        done = next((l.strip() for l in p.stdout if l.startswith(("DONE", "ERR"))), None)
        if not done or not done.startswith("DONE"):
            p.kill()
            sys.exit(f"request {n}: the engine answered {done!r}")
        if (n + 1) % 20 == 0 or n + 1 == len(reqs):
            print(f"{n + 1}/{len(reqs)} requests, {time.time() - t0:.0f} s", flush=True)
    p.stdin.write("QUIT\n")
    p.stdin.flush()
    try:
        p.wait(timeout=300)
    except subprocess.TimeoutExpired:
        p.kill()
    want, got = sum(len(r) - 1 for r in reqs), sum(1 for _ in open(out))
    print(f"{got} positions written, {want} expected")
    return 0 if got == want else 1


def cmd_ppl(a):
    rows, nll, n, line = open(a.tsv), 0.0, 0, 0
    for b, s, e in windows(a.ntokens, a.context, a.stride):
        seg = [rows.readline().split("\t", 3) for _ in range(e - b - 1)]      # line t predicts the window's token t+1
        use = seg[s - b - 1:]
        w = -sum(float(r[2]) for r in use)
        print(f"window [{b},{e}) scored {len(use)}: perplexity {math.exp(w / len(use)):.6f}")
        nll += w
        n += len(use)
    print(f"scored {n} targets, mean NLL {nll / n:.6f}, perplexity {math.exp(nll / n):.6f}")


def kl_over(p, q):
    import numpy as np
    p = p - np.log(np.exp(p).sum())
    q = q - np.log(np.exp(q).sum())
    return float((np.exp(p) * (p - q)).sum())


def report(n, na, nb, same, kls, names):
    import numpy as np
    kls = np.array(kls)
    pa, pb = math.exp(na / n), math.exp(nb / n)
    print(f"scored tokens     {n}")
    print(f"perplexity        {names[0]} {pa:.4f}   {names[1]} {pb:.4f} ({(pb / pa - 1) * 100:+.2f}%)")
    print(f"same top token    {same / n * 100:.2f}%")
    print(f"KL({names[0]} || {names[1]})  mean {kls.mean():.5f}  median {np.median(kls):.6f}  "
          f"p99 {np.percentile(kls, 99):.4f}")


def cmd_vs_llama(a):
    import numpy as np
    f, n_ctx, n_vocab, n_chunk, toks = read_logits_header(a.logits)
    nv, first = 2 * ((n_vocab + 1) // 2) + 4, n_ctx // 2
    rows, na, nb, n, same, kls = open(a.tsv), 0.0, 0.0, 0, 0, []
    for c in range(n_chunk):
        lines = [rows.readline().rstrip("\n").split("\t") for _ in range(n_ctx - 1)]
        for j in range(first, n_ctx - 1):                  # llama-perplexity scores the second half of each chunk
            raw = np.frombuffer(f.read(2 * nv), dtype=np.uint16)
            scale, low = struct.unpack("<ff", raw[:4].tobytes())
            lp = raw[4:4 + n_vocab].astype(np.float64) * scale + low
            tgt, r = toks[c * n_ctx + j + 1], lines[j]
            if int(r[1]) != tgt:
                sys.exit(f"chunk {c} position {j}: the runs are not on the same tokens")
            top = np.argpartition(-lp, 64)[:64]
            sd = {int(k): float(v) for k, v in (x.split(":") for x in r[8:])}
            floor = min(sd.values())                       # a token Strata does not list gets its last listed value
            na -= lp[tgt]
            nb -= float(r[2])
            n += 1
            same += int(r[3]) == int(top[np.argmax(lp[top])])
            kls.append(kl_over(lp[top], np.array([sd.get(int(t), floor) for t in top])))
    report(n, na, nb, same, kls, ("llama.cpp", "Strata"))


def cmd_vs(a):
    import numpy as np
    first, na, nb, n, same, kls = a.context // 2, 0.0, 0.0, 0, 0, []
    for i, (la, lb) in enumerate(zip(open(a.ref), open(a.run))):
        if i % (a.context - 1) < first:
            continue
        ra, rb = la.rstrip("\n").split("\t"), lb.rstrip("\n").split("\t")
        if ra[1] != rb[1]:
            sys.exit(f"line {i}: the runs are not on the same tokens")
        pa = [x.split(":") for x in ra[8:8 + 64]]
        sb = {k: float(v) for k, v in (x.split(":") for x in rb[8:])}
        floor = min(sb.values())
        na -= float(ra[2])
        nb -= float(rb[2])
        n += 1
        same += ra[3] == rb[3]
        kls.append(kl_over(np.array([float(v) for _, v in pa]), np.array([sb.get(k, floor) for k, _ in pa])))
    report(n, na, nb, same, kls, ("REF", "RUN"))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    x = s.add_parser("capture"); x.add_argument("pid", nargs="?"); x.add_argument("out")
    x = s.add_parser("ids")
    for k in ("text", "nbytes", "tokenizer", "strata", "out"):
        x.add_argument(k, type=int if k == "nbytes" else str)
    x = s.add_parser("run"); x.add_argument("engine"); x.add_argument("out")
    x.add_argument("--logits"); x.add_argument("--ids"); x.add_argument("--context", type=int, default=4096)
    x.add_argument("--stride", type=int, default=2048); x.add_argument("--no-cvec", action="store_true")
    x.add_argument("--kv"); x.add_argument("--unset")
    x = s.add_parser("ppl"); x.add_argument("tsv"); x.add_argument("ntokens", type=int)
    x.add_argument("--context", type=int, default=4096); x.add_argument("--stride", type=int, default=2048)
    x = s.add_parser("vs-llama"); x.add_argument("logits"); x.add_argument("tsv")
    x = s.add_parser("vs"); x.add_argument("ref"); x.add_argument("run"); x.add_argument("--context", type=int, default=512)
    a = p.parse_args()
    if a.cmd == "run" and bool(a.logits) == bool(a.ids):
        sys.exit("run: give --logits FILE or --ids IDS.json")
    return {"capture": cmd_capture, "ids": cmd_ids, "run": cmd_run, "ppl": cmd_ppl, "vs-llama": cmd_vs_llama,
            "vs": cmd_vs}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main() or 0)
