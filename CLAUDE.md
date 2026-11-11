# Working in this repository

Two jobs come up here, and this file covers both:

- **Part 1, fitting it to someone's PC:** the phases below, in order
- **Part 2, maintaining it:** the layout, the rules, the test routine and the upstream watch, further down.
  Part 1 uses the test routine too

# Part 1: tuning this repository for another PC

You are helping someone fit this repository to their own computer: one or more GPUs (NVIDIA, AMD, Intel or
Apple) and any amount of RAM. The repository was tuned and measured on exactly one box, an RTX 5090 + RTX 4070 Ti
SUPER with 31 GiB of RAM on Linux. Everything else is transfer, and you must say so wherever it applies.

Work in the phases below, in order. **Phases 1 and 2 are read-only and end with a written assessment. Do not
build, download model or source files, start or stop a server, install a driver or edit a config until the user
has read the assessment and told you to go on.**

## Rules that hold in every phase

- **Label every number** as *measured on the reference box*, *measured by upstream* (name the document) or
  *estimate*. Never present an estimate as a result, and never promise the reference box's numbers
- **When no measured machine is close, give no range.** Say so and propose a baseline measurement. An invented
  range is worse than none
- **Ask before** any download (state its size), any driver or toolkit install, anything outside the repository
  folder, and any setting that changes what the model outputs. Reading web pages is not a download: file
  listings on Hugging Face and upstream's documents on GitHub are allowed in phase 2
- **Output-changing settings are the user's choice, never a silent tuning step.** The shipped configs already
  make several of these choices, so ask about each one in the assessment:
  - the quant, and the K/V precision (never below `int8` without being asked)
  - the control vector: **on in every shipped config, it removes the model's refusals at runtime.** Drop the
    four `--control-vector*` / `--cvec-*` flags if the user does not want that
  - the chat template (Sharp at xhigh effort instead of the model's own) and the `sampling` block
  - upstream's opt-in kernel switches in `env` (the `STRATA_GR_*`, `SCORES_HALVE`, `TOPK_SPLIT`, `QIL`,
    `SIDE_MIXER`, `ATTN_DAILY`, `GU_SWIGLU`, `FUSE_HEAD_GR`, `LFUSE` group): on as shipped. Upstream calls all
    but `GR_V3` bitwise; measured together here they pick the same top token as the same build without them
    96.7% of the time, at equal perplexity (`docs/quality.md`)
  - `STRATA_ROUTE_TAIL_SKIP` (off as shipped, on by default upstream)
- **Context is the user's stated need.** When a lower value would change the tier, say so and let them choose
- **No swapping during a test.** Read `pswpout` from `/proc/vmstat` before and after: a configuration whose
  test routine moves it is rejected, however fast it measures. Swap that was in use before the test is noted,
  not judged. (The shipped IQ3_S config is an older trade that puts about 3.5 GB of engine memory in zram on
  31 GiB; the default config does not, and new configs must not)
- **Never bind the server to a non-loopback address without an API key.** If a server is already listening on
  one (`ss -ltnp`), mention it and ask whether it has a key; you cannot tell from outside
- **Never stop a server you did not start.** If an engine or another model server is running, the survey cannot
  see free memory and nothing here can be built or booted next to it: report it, ask the user to stop it, and
  ask whether its model files can be reused (`MODELS=/path ./install.sh` skips the download)
- **One engine at a time**, started as a service (Part 2), and a change counts only after it is measured there

## Which path applies

Decide this first; it tells you which sections to use.

| Machine | Build | Use from this file |
| --- | --- | --- |
| Two or more NVIDIA cards, Linux | this repository (`install.sh`, patches 01-08 on Strata v0.2.1). Only two cards were ever run; three or four is untested | everything |
| One NVIDIA card, Linux | this repository, or upstream's current release. See "One NVIDIA card" below | phases 1-6; the two-card settings are dropped |
| NVIDIA on Windows | upstream's installer (`START-HERE.bat`). This repository's scripts are bash and were never run on Windows or WSL | phases 1-2 and the HTTP tools |
| AMD (Linux, or Windows with one card) | upstream's current release, `--backend hip` | phases 1-2, the method of phase 5, the HTTP tools |
| Intel Arc | upstream's current release; experimental, Linux, built in Docker | the same |
| Apple silicon | upstream's `./setup.sh`; macOS 15 or newer | the same, with the Apple fit table in 2.1 |
| AMD Strix Halo (Ryzen AI Max, unified memory) | upstream's current release; it recognises the chip and has its own page, `STRIX_HALO.md` | phases 1-2, the unified-memory notes in 2.1, the method of phase 5, the HTTP tools |
| NVIDIA DGX Spark (GB10, ARM, unified memory) | upstream's current release, if it builds. Upstream's v0.2.1 documents name the Spark in one line and publish no measurement; this repository was never built on ARM | phases 1-2 and the HTTP tools. Confidence is the lowest of any row: propose a baseline before anything else |
| Mixed makes (NVIDIA + AMD, any + Intel) | one make per engine: pick the stronger set | as for that make |
| No supported GPU: integrated graphics other than Strix Halo, a card older than RTX 20 or under 8 GB, CPU only | none. Strata's backends are CUDA, AMD HIP, Intel SYCL and Apple Metal, and nothing else: do not suggest another | phases 1-2. This is tier D: say so and stop |

For every row but the first two, `patches/`, `install.sh`, `prepare.sh`, `configs/` and phase 4's flag table do
not apply: they were never compiled on that backend. Take upstream's setup defaults as the starting config and
its own tuning step (`--calibrate`, NVIDIA only for now) as the first lever. What carries over is the survey,
the assessment, the measuring method, and the tools that talk to the server over HTTP (`window_bench.py`,
`prompt_bench.py`, `grow_chat.py`, `tool_probe.py`, `lcb_gen.py`). `tools/snapshot.py` and the swap check read
`/proc` and are Linux-only.

Upstream facts used in this file were read from the Strata v0.2.1 documents (`docs/MODELS.md`, `QUANTS.md`,
`MULTI_GPU.md`, `MAC.md`, `AMD_HIP.md`, `STRIX_HALO.md`, `INTEL.md`, `OLDER_GPUS.md`) on 2026-11-10. Users on
another backend install the current release, so before quoting a limit to them, read the current file at
`https://github.com/Niko1221/Strata/tree/main/docs`:

- one GPU make per engine; a layer split wants 8 GB or more per card and is searched over 2 to 4 cards
- NVIDIA: RTX 20 and newer. Intel Arc: experimental. AMD: RX 7000 / 9000 validated, RX 6800 / 6900 reported
- Apple: M1 or newer; a Mac that streams experts runs without the draft layer; under 16 GB does not fit
- `"layer_split"` is the **first layer of each later card**, not a count: `"39"` puts layers 0-38 on the first
  card and 39-47 on the second

## Phase 1: survey the machine (read-only)

Collect all of this before forming an opinion.

| Fact | Linux | macOS | Windows (PowerShell) |
| --- | --- | --- | --- |
| GPUs, VRAM total and used, driver | `nvidia-smi --query-gpu=index,name,memory.total,memory.used,driver_version --format=csv`; AMD: `/sys/class/drm/card*/device/mem_info_vram_total` and `_used`; any: `lspci -nnk \| grep -A3 -E 'VGA\|3D'` | `system_profiler SPDisplaysDataType` | `nvidia-smi` as on Linux; `Get-CimInstance Win32_VideoController` |
| PCIe link per card | `nvidia-smi --query-gpu=index,pcie.link.gen.max,pcie.link.gen.current,pcie.link.width.current --format=csv` | not applicable | the same `nvidia-smi` query |
| RAM and swap | `grep -E 'MemTotal\|MemAvailable' /proc/meminfo`, `swapon --show`, `grep pswpout /proc/vmstat` | `sysctl hw.memsize vm.swapusage`, `vm_stat` | `Get-CimInstance Win32_OperatingSystem` (total and free memory) |
| CPU layout | `lscpu`; a hybrid Intel CPU has `/sys/devices/cpu_core/cpus` and `/sys/devices/cpu_atom/cpus` | `sysctl -n machdep.cpu.brand_string hw.perflevel0.physicalcpu hw.perflevel1.physicalcpu` | `Get-CimInstance Win32_Processor` |
| Disk | `df -h .`, `lsblk -d -o NAME,ROTA,TRAN,MODEL,SIZE` | `df -h .` | `Get-PSDrive`, `Get-PhysicalDisk` |
| What already holds memory | the `nvidia-smi` process list, `ss -ltnp`, `systemctl --user list-units --type=service`, `pgrep -a strata` | `top -l 1` | Task Manager figures |
| Software | OS and kernel, `nvcc --version`, `cmake`, `ninja`, `git`, Python 3.10+, `docker` if benchmarks are wanted | `sw_vers`, Xcode command line tools | Windows version |

Reading the survey:

- **Units.** Tools report GiB or MiB; boxes are sold in GB. A "24 GB" card is 24.0 GiB, but "32 GB" of RAM is
  about 31 GiB usable and "64 GB" about 62. Do every sum in GiB with the reported figures
- **PCIe.** Quote the **current width** (it is fixed by the slot: the reference 4070 sits on x1 although the
  card supports x16) and the **maximum generation** (the current one drops at idle: the reference 5090 reads
  Gen 1 until it works)
- **Hybrid CPUs.** Do not infer core classes from clock speeds: favoured cores give three or more values
- **Containers and virtual machines.** The limits that count are the guest's: its memory limit, the cores it
  was given, and whether a GPU is passed through at all. Say that the host may have more
- **Disk.** The download must fit on the free disk with room to spare; if it does not, that alone decides the
  verdict
- **Card numbering.** `"gpu": [0, 1]` in a config follows `nvidia-smi`'s numbers, and the first is the main
  card. Confirm it in the boot log, which names the card behind each stage

Then ask the user what the machine cannot tell you:

1. what they use the model for (agents with tool calls, long documents, chat, coding)
2. whether the machine can serve with nothing else open (a login screen, or headless), or must share with a
   desktop and a browser
3. how much context they actually need
4. the output choices listed in the rules: control vector, template, quant preference
5. whether the server must be reachable from other machines (then it needs a key)

## Phase 2: the assessment (then stop)

### 2.1 Does it fit, and in which tier

The model is a mixture of experts: 48 layers of 512, ten used per layer and token. Speed is decided by where
each expert lives:

- **in VRAM:** computed on the GPU. The engine fills the VRAM cache with the experts used most
- **in page-locked RAM:** computed **on the CPU** from the RAM copy. On the reference box the 27% of expert
  bytes that sit in RAM are the coldest ones (0.5 lookups per layer and window), which is why it stays fast. A
  machine with most of its experts in RAM runs a large share of decode on the CPU and is several times slower:
  that placement was never measured with this build
- **on the SSD:** read on demand; the slowest by far

**Expert sizes.** Do not derive these from shard sizes: shards mix experts with dense weights.

| Quant | Experts | Download | Source |
| --- | --- | --- | --- |
| ISTA Q2_0 | 34 | 66 GB | upstream `MODELS.md` (its unit is not stated; treat as GiB, give or take 2) |
| ISTA IQ2_XS | 35.5 | about 68 GB | same |
| ISTA IQ3_XXS | 43 | 76 GB | same |
| ISTA IQ3_S | 50 | about 84 GB | same |
| **Unsloth UD-IQ3_XXS (shipped default)** | **46.84 GiB**, 0.976 per layer, 1.906 MiB per expert | 83.6 GB + 54.4 GB for the Q8_0 n-gram table + 0.9 GB image projector | *measured on the reference box*; sizes from the Hugging Face listings |
| Unsloth UD-IQ4_XS | 55.4 GiB | 93.7 GB | upstream `QUANTS.md` |
| Unsloth UD-Q4_K_XL | 71.7 GiB | 111.3 GB | same; the shipped build turns the K-quant kernels off (`-DSTRATA_MMQ_KQUANTS=OFF`, `-DSTRATA_Q6K_EXPERTS=OFF` in `install.sh`); never built or run here |
| Unsloth UD-Q5_K_XL / UD-Q6_K_XL / Q8_0 | 91.6 / 101.7 / 119.5 GiB | 158 / 169 / 188 GB | same |

The n-gram (PLE) table is separate and stays on the SSD. Model repositories: `unsloth/Qwen3.8-Flash-Next-GGUF`
and `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF`. Quality between quants: upstream's `MODELS.md` and
`QUANTS.md` tables, and the quant notes in `docs/benchmarks.md` and `docs/how-it-works.md` here.
`docs/quality.md` compares this build with llama.cpp and the hosted model on one quant only.

**VRAM that does not hold experts.** *Measured on the reference box* at 262,144 context, images on, drafter on,
as card total minus the experts the boot log says it holds:

| Card | Total | Experts held | Everything else |
| --- | --- | --- | --- |
| First (5090) | 31.84 GiB | 13,180 experts = 24.5 GiB | 7.3 GiB: dense weights, resident K/V (`--kv-resident 32768`), prompt buffers, the 700 MiB reserve |
| Later (4070 Ti SUPER) | 15.99 GiB | 4,608 = 8.6 GiB, all nine of its layers | 7.4 GiB: dense weights, the whole K/V of its layers, the drafter, the image encoder (1.28 GB), the output head, the 420 MiB reserve |

Only these totals were measured. There is no per-token figure for context and no one-card figure: a shorter
context, no images or one card each free an unknown part. Use 7 GiB per card of a split as the estimate, and
8 to 10 GiB for one card that carries everything (the drafter, the output head and the image encoder then sit
on it too). Correct it from the first boot log, which prints the expert count per card.

**RAM that cannot hold experts.** *Measured on the reference box* at 262,144 context:

- the engine needs about 11 GiB of RAM besides the expert copy (its heap and the pinned K/V of
  the long context): the service peaked at 25.7 GiB with 14.7 locked. This matches upstream's "experts plus about 10 GB"
- the engine sizes the copy at boot from the RAM available then, and clamps the budget itself: with 20.0 GiB
  available it cut 13.2 to 11.5 GiB, so about **MemAvailable at boot minus 8.5 GiB** is the most it will lock
- at the login screen 26.4 to 27.7 GiB was available, 14.7 was locked, and the 256K chat ended with 1.7 GB
  left. A desktop with a browser took about 7 GiB of that

So, as an *estimate*: **lockable RAM = MemAvailable with the machine as it will serve, minus about 12 GiB**
(11 for the engine, 1 spare). A shorter context returns part of the pinned K/V; how much was not measured.

**Place the machine.** Experts outside VRAM = expert size minus the sum over cards of (VRAM minus about 7 GiB).

| Tier | Condition | What to expect, and how firm it is |
| --- | --- | --- |
| A | every expert fits in VRAM | best case, RAM barely matters. Nearest measurement: ISTA Q2_0 all in VRAM on the reference box, 211 tokens per second on an older build |
| B | experts outside VRAM, plus the prompt loan, fit in lockable RAM | decode never reads the SSD. Reference box: 27% of experts in RAM, about 250 tokens per second. The larger the RAM share, the more decode runs on the CPU |
| C | some experts stay on the SSD | decode is SSD-bound. Reference points: 2.2 GiB on the SSD cost 26% per window here; upstream's default setup on the reference box, 11 GiB on the SSD, 85 tokens per second. This repository's gains mostly do not apply |
| D | far below fit: under upstream's 32 GB of RAM plus VRAM, or tier C with most experts on the SSD | say plainly that this model is a poor fit for the machine, name what upstream offers for it (its Coder and Gyro sizes, `MODELS.md`), and stop. Ask only whether they want to go on anyway; the other questions wait for a yes |

In tier B always state the share of experts in RAM. Above about half, say that most of decode then runs on
the CPU, that this was never measured with this build, and quote the RTX 5070 row below (12 GB card, 64 GB of
RAM: 62 tokens per second on IQ3_XXS) as the nearest measurement, not the reference box.

Say which neighbouring quant would change the tier and what it costs. A machine within 1 GiB of a tier edge is
"borderline": the first boot log decides, and the assessment says so.

**Apple** does not use these tiers: memory is unified and Metal keeps about three quarters of it resident.
*Measured by upstream* (`MAC.md`):

| Pack | Needs about | Recommended from |
| --- | --- | --- |
| Q2_0 | 46 GB | 64 GB |
| IQ3_XXS | 55 GB | 74 GB |
| IQ3_S | 63 GB | 96 GB |
| UD-Q4_K_XL | 91 GB | 128 GB |

Below that the Mac streams experts from the SSD, without the draft layer.

**Strix Halo and DGX Spark** are unified-memory machines too: one card, and its "VRAM" is the same RAM. The
tiers, the layer split, the RAM copy sized against VRAM and every two-card setting in this file do not apply.
What decides the fit is expert size against total memory, as on a Mac:

- on Linux the engine counts as GPU memory what the system can give back, `MemAvailable` minus 6 GiB
  (`STRATA_UMA_HEADROOM_GIB`); upstream says the same rule covers a DGX Spark (`STRIX_HALO.md`)
- Strix Halo, *measured by upstream* on a 128 GB box: every expert in memory, and setup recommends UD-IQ4_XS
  from about 80 GB. By default the GPU may use about half the RAM, on Linux and on Windows; raising it on Linux is a kernel boot
  setting (`ttm.pages_limit`), which is the user's decision and outside this repository
- at 128 GB the larger quants fit where no card pair holds them, so quality is what such a machine buys, not
  speed (the measured rows below: 43 to 60 tokens per second)
- DGX Spark: read the compute capability with `nvidia-smi --query-gpu=name,compute_cap --format=csv` and check
  upstream's current documents and issues for it before saying anything about speed

**Measured machines to anchor an estimate on.** Quote the nearest, with its engine version, and say how the
user's machine differs. If none is near, give no range.

| Machine | Quant, placement | Decode | Prompt | Source |
| --- | --- | --- | --- | --- |
| RTX 5090 + 4070 Ti SUPER (x1 link), 31 GiB | UD-IQ3_XXS, tier B, 262K | 250 tok/s | 80K in 15.4 s, 250K in 46.7 s | this repository |
| the same box, upstream v0.2.13 defaults | UD-IQ3_XXS, tier C, stock template | 85 tok/s | 80K in 89.2 s | `docs/benchmarks.md` |
| RTX 5070 12 GB, 64 GB RAM | Q2_0 / IQ3_XXS / IQ3_S, most experts in RAM | 94 / 62 / 53 tok/s | 32K at 2,650 / 1,750 / 1,620 tok/s | upstream `MODELS.md`, engine 0.1.26, old |
| RX 9070 XT 16 GB, 47 GB RAM, Linux | Q2_0 / IQ2_XS | 60 / 52 tok/s | 32K at about 1,100 tok/s | upstream `MODELS.md` |
| 2 x RTX 3090, x16 + x4 links | split 27 | 130-136 tok/s | not given | upstream `MULTI_GPU.md` (#2418) |
| Radeon AI PRO R9700 32 GB, every expert in RAM | UD-Q4_K_XL | 63 (story) / 87 (code) tok/s | 32K at 1,110-1,320 tok/s | upstream `MODELS.md` |
| Ryzen AI Max+ 395 (Strix Halo), 128 GB, Linux | IQ3_XXS / IQ3_S / UD-IQ4_XS / UD-Q4_K_XL, all in memory | 51 / 60 / 54 / 53 tok/s at 8K; 51 / 43 / 51 / 43 at 128K | about 1,250-1,320 tok/s | upstream `STRIX_HALO.md` |
| M5 Max, 128 GB | Q2_0 / IQ3_XXS, in memory | 108-120 / 97-109 tok/s | 32K at 1,460 / 1,240 tok/s | upstream `MAC.md` |
| M1 Max, 34 GB | Q2_0, streamed | 7.9 tok/s | 186 tok/s | upstream `MAC.md` |

### 2.2 What to tell the user

Write the assessment in this shape, in plain language, and then wait:

1. **Your machine:** the survey, one line per row that matters, plus anything already running
2. **Verdict:** the path from the table above, the tier with its arithmetic shown, the quant and context you
   recommend
3. **Expected results:** the nearest measured machine and how theirs differs; a range only when that machine is
   close, marked estimate
4. **How sure this is:** high when the hardware is close to a measured box, low otherwise. Name each part of
   the plan that has never been run on hardware like theirs
5. **Left on the table:** every limit you found and what would lift it: more RAM (how much moves them a tier), a
   card on a narrow PCIe link, a desktop holding VRAM and RAM, a neighbouring quant, a feature their backend
   lacks, K-quant files needing a rebuild
6. **What I would do next:** each download with its size (the draft layer adds about 6 GB, `MODELS.md`), every
   folder it writes, and the number of server boots the tuning needs (phase 5 is about 10 to 15). No build,
   boot or benchmark durations are recorded in this repository: say that, time the first of each, and report it
7. **What I need from you:** the output choices from the rules, the context, anything that must be stopped or
   closed, and a go-ahead

## Phase 3: install (after the go-ahead)

- **NVIDIA on Linux:** `./install.sh` with `CUDA_ARCHS` set for the cards present (RTX 20: 75, RTX 30: 86,
  RTX 40: 89, RTX 50: 120, several joined with `;`) and `JOBS` sized to RAM (a compile job takes about 3 GB).
  Only 89 and 120 were built here. Then the model download and `./prepare.sh` from the README. The patched tree
  must match `patches/MANIFEST.sha256`; if it does not, stop. The README's Status section says which parts of
  the install were never run end to end
- **Every other path:** clone upstream Strata into its own folder and follow its setup for that hardware. Its
  `--check` is safe in a fresh clone. **Never run upstream's setup, with or without `--check`, inside this
  repository's `strata/` folder or any tree in use:** on the reference box it moved the prepared packs and
  drafter out of a working tree
- Write the user's configuration as a **new file**, copied from `configs/flash-next-ud-iq3xxs-262k.json.in`
  and changed only where phase 4 says. Never overwrite a shipped config

## Phase 4: the starting configuration (NVIDIA on Linux)

Copy the shipped default and change these. The rules come from one box; treat them as starting points that
phase 5 corrects.

| Setting | Starting value | Basis |
| --- | --- | --- |
| `"gpu"`, card order | the bigger, faster card first, `"gpu_order": "as_given"`, with `--prefill-main` so prompts are read there | measured here with the second card on an x1 link. Upstream's `auto` puts the faster card last; with equal links test both |
| `"layer_split"` | first layer of the later card = 48 minus the whole layers it can hold: floor((its VRAM in GiB - 7) / per-layer size). The first card then caches (its VRAM - 7) GiB of its own layers' experts and the rest of them goes to RAM | reference box: floor((15.99 - 7) / 0.976) = 9, split 39. `"auto"` is the alternative start |
| `--resident-experts --resident-budget-gib N` | N = experts outside VRAM + the prompt loan, capped at lockable RAM (2.1). If N exceeds the cap the machine is tier C | here 12.83 + 1.87 = 14.7. The boot log says when the engine clamped it |
| `--prefill` chunk (a literal number; `auto:4096` silently picks 8192) | 4096 when RAM is tight; larger when the bigger loan still fits | loans on the 5090, *measured here*: 962 slots = 1.87 GiB at 4096; 1,543 slots at 8192 (about 3 GiB, scaled); 6,243 = 9.77 GiB at 32768 on ISTA IQ3_XXS. The boot log prints the count and how many have a RAM copy |
| `STRATA_RESIDENT_HEADROOM_GIB` | 3 as shipped when nothing else runs; 14 when a desktop is used while it serves | `docs/tuning.md`: the higher value keeps the desktop responsive, prompts about 40% slower |
| `--vram-reserve-mib`, `--vram-reserve-later-mib` | as shipped (700, 420); raise the first by what a desktop holds on that card | sized here for a login screen |
| `"vision": {"cuda_device"}` | the card with spare VRAM after the split; drop `--vision` and the block if images are not needed | 1.28 GB on the 4070, 1.7 GB on the 5090 |
| `--kv-resident-later 0`, `--trim-stage-weights`, `--pipeline-windows 2 --adapt-async 1`, `--prefill-main-small 512`, `STRATA_PM_MTP_BATCH`, `STRATA_RESIDENT_LEND` | on for a two-card split | measured here |
| `--aux-cpus auto --host-core sibling` | on for CPUs with performance and efficiency cores | 11.0 to 10.2 ms per window here; expect nothing on a uniform CPU |
| Conversation parking, SSD spill, prefix store | off when lockable RAM is fully used by experts. With RAM to spare, turn them on with the flags of the IQ3_S config: 1 GiB parks chats up to about 50K tokens, and `docs/tuning.md` suggests 6 GiB or more at 64 GB of RAM | they cost RAM the long context needs |
| `--max-context` | what the user chose | the full 262,144 costs VRAM and RAM that could hold experts |
| Keep as shipped | `--kv int8`, `--kv-resident 32768`, `--short-read 128`, `--lookup-chain 4`, `--spec 4 --spec-min-p 0.8`, `--mtp-hnorm stream`, the `MALLOC_*` and `STRATA_PL_*` variables, `STRATA_RAM_ADAPT`, `"fit_max_tokens"`, `"STRATA_ROUTE_TAIL_SKIP": "0"`, `"STRATA_HC_Q8": "0"`, `"presence_penalty": 0.0` | the last two break tool calls or slow decode on this build (README, Run) |

Worked example, two equal 24 GiB cards and 31 GiB of RAM (*estimate*, never run): later card
floor((24 - 7) / 0.976) = 17 layers, split 31, 16.6 GiB; first card 17 GiB; outside VRAM 46.84 - 33.6 = 13.2;
budget 13.2 + 1.9 = 15.1 against 14.4 to 15.7 lockable at a login screen (26.4 to 27.7 available, minus 12). Borderline B/C: say so, and offer a
lower context or ISTA IQ3_XXS as the ways to make it safe.

### One NVIDIA card

Never run with this build. Tell the user that, and offer both routes:

- **Upstream's current release** with its setup and `--calibrate`: the tested route for one card. Take it when
  the user mostly chats, or when the machine is tier C
- **This build:** worth trying when tool calls matter (the parser and template work here scored 30/30 on the
  tool probe against 9/30 for stock v0.2.13 with its stock template on the reference box). Whether that
  survives on one card is unmeasured

For this build on one card, from the shipped default: set `"gpu": [0]`, remove `"layer_split"`,
`--kv-resident-later`, `--vram-reserve-later-mib`, `--prefill-main`, `--prefill-main-small`,
`--prefill-main-small-max`, `--trim-stage-weights`, `--pipeline-windows`, `--adapt-async`,
`STRATA_PM_MTP_BATCH` and `STRATA_RESIDENT_LEND`, and set the vision device to 0. Whether the prompt path
borrows cache slots on one card is not known here: read the boot log before sizing the budget for a loan.

## Phase 5: tune by measuring

One change, one fresh boot, one measurement. The routine, the tools and the pass marks are in Part 2.

1. **Baseline twice.** Boot the starting config, run `tools/window_bench.py` on two separate boots. The
   difference between them is your noise; a change must beat it to be kept
2. **Fit first.** Read the boot log: the expert count per card, the RAM copy's size, any budget clamp, how many
   borrowed prompt slots have a RAM copy, and after a few requests the line that reports blob reads from the
   file. Correct the phase 2 arithmetic with these, then tune the budget, the context and what else runs on
   the machine until decode reads nothing from the SSD, or until you have shown that it cannot (tier C)
3. **Split,** plus or minus one or two layers, when there is more than one card
4. **Prompt chunk** and `--prefill-main` on or off, measured with `tools/prompt_bench.py`
5. **Thread placement**
6. **The kernel switches:** they start on, as shipped. If the user asked for exact output, turn the group off
   and measure what it costs (about 4.5% per window here, measured on IQ3_S). On other hardware a switch may lose: test the group
   off once, and bisect only if off is faster
7. **The full test routine** from Part 2 on the final config, including the long chat to the context limit with
   the swap counter read before and after

Rank by milliseconds per verify window, not tokens per second, when the drafter is involved. Stop when two
rounds in a row bring nothing beyond noise.

## Phase 6: hand over

- A before and after table: starting config, final config, and for each row whether it was measured or carried
  over. Include the runs that lost, and the build, boot and benchmark times you recorded
- The final config file, the launch command, and what must be true at boot (headless or not, what must be
  closed)
- Offer to format the results as an issue for this repository: hardware, quant, context, the table, the config.
  Results from other machines are what would make this guide better

## Traps that cost hours on the reference box

- An out-of-memory kill takes the terminal session with it. Start the server as a service, not from your shell
- `/health` answers on a dead engine. Liveness is a real chat request
- The RAM copy is sized once at boot. Whatever holds memory at that moment (a browser, a desktop) shrinks it
  for the whole session. The copy does not show in `VmLck`; the boot log is the only place that states its size
- The first request after a fresh prompt is 10 to 15% slower than the next. Send a settle request before timing
- Speculative-decoding acceptance swings several points between identical boots, and tokens per second with it
- Graders and builds running next to a loaded model push it into swap. Stop the server for those
- `tools/window_bench.py` and the README call its long prompt "20K"; it is 15,000 random words, about 50K
  tokens. Compare it only with itself

# Part 2: maintaining this repository

## Layout

| Path | What it is |
| --- | --- |
| `patches/` | the series applied to Strata v0.2.1 in order; `MANIFEST.sha256` is the tested tree, checked in CI |
| `install.sh`, `prepare.sh`, `launchers/` | clone, patch and build into `./strata`; prepare the model; serve on `:8888` |
| `configs/*.json.in` | the shipped server configs, `@MODELS@` filled in by `install.sh` |
| `tools/` | the measuring scripts ([docs/tools.md](docs/tools.md)) |
| `docs/` | [benchmarks](docs/benchmarks.md), [quality](docs/quality.md), [tuning](docs/tuning.md), [patches](docs/patches.md), [how it works](docs/how-it-works.md) |

## Rules

- Every number in the README and docs was measured. A change to a number needs a new measurement, and the
  docs, the README and `tools/make_comparison_chart.py` change together
- A patch change must keep `patches/MANIFEST.sha256` true: applying the series to a pristine v0.2.1 checkout
  rebuilds the tested tree byte for byte
- Nothing that changes model output ships as a default without a quality row in `docs/quality.md`
- Never commit model files, keys, benchmark dumps (`tools/agentic-*.json`, `tools/results.jsonl`) or local paths
- Commit and push only when the user asks

## Running the server for a test

```bash
systemd-run --user --unit=strata --collect --working-directory="$PWD" launchers/flash-next-262k.sh
systemctl --user stop strata        # between arms: every arm is a fresh boot
```

- A service, not a shell child: an out-of-memory kill of the engine otherwise takes the session with it
- Ready means a real chat request answered, not `/health`
- One engine at a time. Stop it before anything memory-hungry (a build, a grader, llama.cpp)
- For results to compare with the README, boot at the login screen with no desktop session

## The test routine

Run after any change to a patch, a config or the engine version. Reference values are the shipped config on the
reference box, booted at the login screen.

| # | Test | Command | Reference | Reject the change when |
| --- | --- | --- | --- | --- |
| 1 | Decode gate | `tools/window_bench.py TAG` | 10.2 ms per verify window, 250 tokens per second (median of 7), its long prompt in 10.3 s | ms per window is worse than the baseline's own run-to-run spread |
| 2 | Long prompts | `tools/prompt_bench.py 23700 74000` | 80K in 15.4 s, 250K in 46.7 s, needle returned on both | the needle is missed, or prompt time regresses |
| 3 | Long chat | `tools/grow_chat.py` | 56 turns to 256K, 2.1 s median per turn, 1.7 GB of RAM still available at the end | any swap-out (`grep pswpout /proc/vmstat` before and after), an OOM, or a turn time that climbs |
| 4 | Tool calls | `tools/tool_probe.py 30` | 30 / 30 | fewer than the baseline on the same day (run it twice: the model's own misses are noise) |
| 5 | Output agreement | `tools/engine_logprobs.py` as in [docs/quality.md](docs/quality.md) | perplexity 3.2115 on the 100 chunks; byte-identical between two runs of the same settings | perplexity moves, or agreement with the previous build drops and the change was meant to be exact |
| 6 | After a boot | the engine log | the RAM copy at its full budget, zero blob reads from the file during decode | experts are read from the SSD in decode |

How to compare two arms:

- One change per arm, each arm a fresh boot, the baseline measured on the same day
- Send a settle request after every fresh prompt; the first request after one is 10 to 15% slower
- Rank by milliseconds per verify window. Tokens per second moves with the drafter's acceptance, which swings
  several points between identical boots
- Per-request settings can be paired on one boot with `tools/paired_ab.py`, which rotates the order
- `tools/snapshot.py` before and after a run gives page faults, swap and SSD reads; an arm that reads more from
  the SSD for the same work is slower for a reason you can name
- Tests 1 to 4 need the server; test 5 needs it stopped

Record a kept change in `docs/benchmarks.md` with its date, both arms and the arms that lost.

## The upstream watch

Strata moves fast. This repository stays on v0.2.1 on purpose and carries
later fixes as patches. The watch decides what to carry.

**Last reviewed: pull requests and issues up to #5681 on 2026-11-09, upstream v0.2.13 (engine 0.1.59). The next
check starts at #5682.** Update this line at the end of every check.

```bash
gh release list -R Niko1221/Strata --limit 5
gh pr list -R Niko1221/Strata --state all --limit 300 --search "sort:created-desc" --json number,title,state,mergedAt,additions,deletions
gh issue list -R Niko1221/Strata --state all --limit 300 --search "sort:created-desc" --json number,title,state,createdAt
gh pr view N -R Niko1221/Strata --json title,body,files     # then gh pr diff N for the ones that matter
```

Read every title from the last reviewed number up, open the ones that touch what this build uses, and sort each
into one of four bins:

| Bin | Goes there when | What to do |
| --- | --- | --- |
| Port | a fix for a bug this configuration can hit (layer split on two cards, `--prefill-main`, `--pipeline-windows`, `--adapt-async`, the RAM copy, int8 K/V, the tool-call parser, the PLE table reads) | cherry-pick onto the patched tree, add it as the next numbered patch, run the test routine |
| Test later | a speed change on a path this build runs, with the author's own measurement | note the number, the claimed gain and the hardware it was measured on; A/B it when there is time |
| Skip | another backend, another quant family, a feature that is off here (parking, spill, parallel slots, the peer device), docs, installers, UI | one line saying why |
| Risk to watch | an open issue that matches this configuration's flags, whether or not it has been seen here | note the symptom, the trigger and a fallback setting |

What matters when reading one:

- **Does it change output?** Upstream marks byte-identical changes as such. Anything else needs test 5 before it
  ships, and stays opt-in until then
- **Whose hardware measured it?** A gain on four equal cards or on AMD says little about a 32 + 16 GB pair with
  the second card on a PCIe x1 link
- **Is it already here?** Several upstream changes are later versions of patches this series carries; a port
  then replaces part of patch 01, it does not stack on it
- **A version bump is a separate decision.** Upstream issues after v0.2.1 report regressions on layer splits
  (prompt and decode speed on two-card setups, load-time RAM peaks). Before proposing one, measure the stock
  release against this build with the whole test routine, as `docs/benchmarks.md` did for v0.2.13

Porting, step by step:

1. In a scratch copy of the patched `strata/` tree, apply the upstream change and resolve conflicts by hand
2. Build, boot, and run the test routine against a same-day baseline
3. Export the result as the next `patches/NN-*.patch`, regenerate `patches/MANIFEST.sha256` from the patched
   files, and confirm a pristine v0.2.1 checkout plus the whole series reproduces the tree
4. Describe it in `docs/patches.md` (source, what it fixes, what was measured) and add the row to the README's
   patch table

Never run upstream's `setup.py` or `setup.sh` inside a tree you use, not even with `--check`: it reorganises the
data folders and has moved the prepared packs and drafter out of a working tree. Give a stock install its own
clone and its own data folder.
