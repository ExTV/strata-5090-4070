#!/usr/bin/env python3
"""Draws docs/comparison-light.svg and docs/comparison-dark.svg: this build against upstream Strata as its own
setup installs it, on the same PC with the same model files, and three output quality checks.  The numbers are in
DATA and QUALITY below, from docs/benchmarks.md and docs/quality.md; change them there and here together, then run
this again.

    tools/make_comparison_chart.py
"""
import os
# (title, unit note, this build, upstream, value format, higher is better)
DATA = [
    ("Decode speed", "tokens per second, median of 7 answers", 251, 85, "{:.0f}", True),
    ("20K-token prompt", "seconds to read", 10.3, 65.0, "{:.1f} s", False),
    ("80K-token prompt", "seconds to read", 15.4, 89.2, "{:.1f} s", False),
    ("250K-token prompt", "seconds to read", 46.7, 257.4, "{:.1f} s", False),
    ("Turn in a chat grown to 256K", "seconds per turn, median of 56", 2.1, 12.7, "{:.1f} s", False),
    ("Tool-call probe", "sequences passed, of 30", 30, 9, "{:.0f} / 30", True),
]
# Output quality (docs/quality.md): (title, unit note, this build, reference, reference label, format, higher is
# better, the line under the bars)
QUALITY = [
    ("Perplexity", "25,500 WikiText-2 tokens", 3.2115, 3.2079, "llama.cpp", "{:.4f}", False,
     "0.11% apart"),
    ("Same top token as llama.cpp", "percent of 25,500 positions", 95.1, 95.2, "Untuned", "{:.1f}%", True,
     "not token-identical, tuned or not"),
    ("LiveCodeBench v6", "problems solved of 175, thinking off", 109, 118, "API", "{:.0f} / 175", True,
     "62.3% against 67.4%, p = 0.12"),
]
THEMES = {
    "light": dict(bg="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781", base="#c3c2b7", ours="#2a78d6", theirs="#eb6834", ref="#898781"),
    "dark": dict(bg="#1a1a19", ink="#f0efec", ink2="#c3c2b7", muted="#898781", base="#383835", ours="#3987e5", theirs="#d95926", ref="#898781"),
}
W, COLS, PW, PH, X0, Y0, GX, GY = 1000, 3, 300, 150, 30, 118, 20, 22
LABEL_W, BAR_MAX, BAR_H = 66, 150, 14
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

def bar(x, y, w, color):
    r = min(4, w / 2)   # square at the baseline, rounded at the data end
    return (f'<path d="M{x},{y} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} v{BAR_H - 2 * r} a{r},{r} 0 0 1 -{r},{r} h-{w - r:.1f} z" '
            f'fill="{color}"/>')

def panel(t, px, py, title, note, higher, bars, fmt, caption):
    o = [f'<text x="{px}" y="{py + 18}" font-size="15" font-weight="600" fill="{t["ink"]}">{title}</text>',
         f'<text x="{px}" y="{py + 36}" font-size="12" fill="{t["muted"]}">{note}, {"higher" if higher else "lower"} is better</text>']
    top = max(v for _, v, _ in bars); bx = px + LABEL_W
    o.append(f'<line x1="{bx}" y1="{py + 50}" x2="{bx}" y2="{py + 108}" stroke="{t["base"]}" stroke-width="1"/>')
    for j, (name, v, color) in enumerate(bars):
        y = py + 56 + j * 28; w = max(3, BAR_MAX * v / top)
        o += [f'<text x="{px}" y="{y + 11.5}" font-size="12" fill="{t["ink2"]}">{name}</text>', bar(bx, y, w, color),
              f'<text x="{bx + w + 7:.1f}" y="{y + 11.5}" font-size="13" font-weight="600" fill="{t["ink"]}">{fmt.format(v)}</text>']
    o.append(f'<text x="{bx}" y="{py + 130}" font-size="12.5" fill="{t["ink2"]}">{caption}</text>')
    return o

def draw(t):
    rows = (len(DATA) + COLS - 1) // COLS
    QY = Y0 + rows * PH + (rows - 1) * GY + 30          # the quality section's heading
    H = QY + 44 + PH + 82
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}" role="img" '
         f'aria-label="This build against upstream Strata v0.2.13 on the same PC: six speed measurements and three output quality checks">',
         f'<rect width="{W}" height="{H}" rx="10" fill="{t["bg"]}"/>',
         f'<text x="{X0}" y="42" font-size="22" font-weight="600" fill="{t["ink"]}">Same PC, same model files: this build against upstream Strata</text>',
         f'<text x="{X0}" y="66" font-size="13.5" fill="{t["ink2"]}">RTX 5090 + RTX 4070 Ti SUPER, 31 GB of RAM. Qwen3.8-Flash-Next UD-IQ3_XXS at the full 262,144-token context.</text>',
         f'<rect x="{X0}" y="82" width="12" height="12" rx="2" fill="{t["ours"]}"/>',
         f'<text x="{X0 + 18}" y="93" font-size="13" fill="{t["ink"]}">This build (Strata v0.2.1 + 8 patches, tuned config)</text>',
         f'<rect x="{X0 + 350}" y="82" width="12" height="12" rx="2" fill="{t["theirs"]}"/>',
         f'<text x="{X0 + 368}" y="93" font-size="13" fill="{t["ink"]}">Upstream v0.2.13 (engine 0.1.59), as its own setup installs it</text>']
    for i, (title, note, ours, theirs, fmt, higher) in enumerate(DATA):
        ratio = ours / theirs if higher else theirs / ours
        gain = f"{ours - theirs:.0f} more passed" if "probe" in title else f"{ratio:.1f}x faster"
        o += panel(t, X0 + (i % COLS) * (PW + GX), Y0 + (i // COLS) * (PH + GY), title, note, higher,
                   (("This build", ours, t["ours"]), ("Upstream", theirs, t["theirs"])), fmt, gain)
    o += [f'<line x1="{X0}" y1="{QY - 22}" x2="{W - X0}" y2="{QY - 22}" stroke="{t["base"]}" stroke-width="1"/>',
          f'<text x="{X0}" y="{QY + 6}" font-size="17" font-weight="600" fill="{t["ink"]}">Output quality of this build</text>',
          f'<rect x="{X0 + 350}" y="{QY - 5}" width="12" height="12" rx="2" fill="{t["ref"]}"/>',
          f'<text x="{X0 + 368}" y="{QY + 6}" font-size="13" fill="{t["ink"]}">Reference, named on each bar</text>']
    for i, (title, note, ours, ref, ref_name, fmt, higher, caption) in enumerate(QUALITY):
        o += panel(t, X0 + i * (PW + GX), QY + 22, title, note, higher,
                   (("This build", ours, t["ours"]), (ref_name, ref, t["ref"])), fmt, caption)
    fy = H - 66
    o += [f'<text x="{X0}" y="{fy}" font-size="11.5" fill="{t["muted"]}">Measured 2026-11-10, each server freshly started at the login screen, thinking off, temperature 0. Upstream: both cards, 262,144 context,</text>',
          f'<text x="{X0}" y="{fy + 16}" font-size="11.5" fill="{t["muted"]}">images on, every other setting its own default. One run per bar (decode: 3 runs here, 2 upstream). Details: docs/benchmarks.md</text>',
          f'<text x="{X0}" y="{fy + 32}" font-size="11.5" fill="{t["muted"]}">Quality: llama.cpp on the same files; Untuned = this build with its tuning switches off; API = the hosted Qwen3.8 Flash at full size,</text>',
          f'<text x="{X0}" y="{fy + 48}" font-size="11.5" fill="{t["muted"]}">against this 3.5-bit quant (a gap inside the noise of 175 problems). Details: docs/quality.md</text>',
          '</svg>']
    return "\n".join(o) + "\n"

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
for name, t in THEMES.items():
    open(os.path.join(out, f"comparison-{name}.svg"), "w").write(draw(t))
    print("wrote docs/comparison-%s.svg" % name)
