# How it works

Why each piece is there, in the order the problems appeared. Hardware: RTX 5090 32 GB (CUDA0, PCIe
5.0 x16) and RTX 4070 Ti SUPER 16 GB (CUDA1, chipset slot, Gen3 x1, 0.8 GB/s measured), i7-14700K,
31 GB RAM, one NVMe for the model and the swap file.

## The model and Strata's layout

Qwen3.8-Flash-Next is a 48-layer MoE with 128 experts per layer, 4 active, plus a PLE table. The
ISTA GSQ-RCO IQ3_XXS GGUF is 76 GB: 47 GB of experts in shard 1, 28.8 GB of PLE in shard 2. Strata
keeps a dense pack (attention, norms, embeddings, 1.5 GB) and an expert cache in VRAM, and reads
the experts it does not have from the GGUF, which is mmap'd (`--mmap-experts`), through a CPU
pool of 19 workers. The 5090's expert cache holds 15,233 expert pairs (23.86 GiB) and the 4070's
5,217 (9.49 GiB) for its 12 layers. KV is int8 with 32,768 cells per attention layer resident in
VRAM and the rest in 3 GB of pinned RAM (`--kv int8 --kv-resident 32768`). The MTP drafter
(`--spec 4`, the base model's head packed to Q2_0) runs on the last stage.

## Why layer split 36

With `--layer-split`, CUDA0 runs layers 0-35 and CUDA1 layers 36-47 plus the head and the drafter.
Splits 35 to 39 were swept on stock 0.1.33 with the same 80K-prompt bench: 36 had the best decode
(109 median), 38 the best prefill (+33%) at -14% decode. The 4070 cannot cache all 6,144 pairs of
12 layers (5,217 fit), so moving layers off it helps prompts and hurts decode. 36 is the decode
pick; prompts were fixed another way.

## The prompt bottleneck and `--prefill-main`

On stock Strata a prompt is read through both cards, each handling its own layers. The 4070 on a
x1 link streams every expert it lacks at 0.8 GB/s, so during an 80K prompt the 4070 sat at 100%
and the 5090 idle, and `--prefill 1024` (smaller chunks) was 3x worse. Strata PR #269 reads the
whole prompt on CUDA0 instead (`--prefill-main`); 0.1.33 carves each session to its own layer
range, so the port rewrites `session_copy_layers` to move only CUDA1's layers (QSA K/V rows in
pinned host memory, the GDN state, the position bookkeeping) between the two sessions, in both
directions, and only the cells written since the last copy (`pm_synced`). The drafter's rows are
copied in 256-row pieces because GeForce cards have no peer copies and a single 512 MB buffer on
the 4070 ran out of memory. After the copy the 4070's KV residency map is evicted from the first
rewritten block only (`kv_stream_evict_from`), so its decode keeps hitting VRAM (99.7% measured,
visible in the new `KV streaming (CUDA1)` log line).

Measured: 80K fresh prompt 1,791 tok/s vs 896 on stock, same box state, same day. The 5090's
cache does not hold layer 36-47 pairs (`STRATA_PM_SHARE=1` would make it, and was rejected: the
decode-hot pairs of layers 0-35 get evicted and decode after a big prompt fell to 28 tok/s; it also
restores a pre-prompt snapshot of the residency table after the prompt, which is only safe while
those rows are empty, as they are without the knob). The cost of the full-range session on the big
card: the small card's 12 layers have their pinned host K/V in both sessions, about 0.77 GiB extra.

## Conversation parking with a layer split

Strata parks a conversation's state in RAM (`--conversation-cache-mib`) so that switching between
chats restores it instead of re-reading it, but refuses the option with `--layer-split`. With
`--prefill-main` the whole state exists on CUDA0 right after any prompt, so the port parks CUDA0's
session (after syncing the stage's layers into it) and, on restore, copies the stage's layers back
to CUDA1. Two conversations of 30K and 15K alternating for four rounds: every answer correct,
switches 0.6-1.2 s. A snapshot is 0.8-1.7 GB per 30K tokens; the budget is 6 GB / 8 slots, which
holds two long conversations (a phone and a desktop client, say).

## Why PR #439 is left out

Upstream's batched expert gathers (`gather_native_batch`, +4% prefill) defer giving ring slots
back until a group's gathers launch. Under `--prefill-main`, layer 46 of the second full 8192-token
chunk of an 80K prompt hung three times out of three (engine watchdog, "no progress for 60 s"),
with the expert pool idle and the host waiting on a GPU event; the 2K and 16K prompts passed. The
same binary with `STRATA_PREFILL_GATHER_ONE=1` (one launch per expert) passed, and so did
`STRATA_PM_SHARE=1`, where that layer streams far fewer experts. The exact ordering bug was not
chased; the patch is simply not applied.

## spec-min-p

`--spec-min-p` shortens a draft when the drafter's probability for the previous draft token falls
below it (`generate.cpp`, the `req_spec_min_p` loop); verification still decides every token, so
it changes speed only. At temperature 0.6: 0.3 / 0.5 / 0.7 gave 78 / 114 / 128 tok/s median and
0.7 / 0.8 / 0.9 gave 97 / 134 / 121 in a second, noisier sweep (0.8 beat 0.7 on 4 of 5 prompts).
0.8 is the config. A request can override it with `"strata_tune": {"spec_min_p": x}`.

## RAM pressure: what it was and what fixed it

The counters that matter are `pgmajfault` and `pswpin` from `/proc/vmstat` around a prompt
(`tools/snapshot.py`). Expert-cache sizes were identical on every boot, so it was not VRAM; parking
budget 6 GB vs 2 GB vs off did not separate fast boots from slow ones; `vm.swappiness=10` did not
either. Two things did:

1. **Prompt chunk size.** Each chunk re-streams the experts of every layer, so an 80K prompt in
   8,192-token chunks streams the ~15 GB working set ten times. `--prefill auto:32768` streams it
   three times: 510 -> 1,451 tok/s and 24 M -> 1.1 M faults on the same afternoon (16384: 1,337).
2. **`pread` instead of page faults** (`patches/11-pread-expert-blobs.patch`, on with
   `STRATA_BLOB_PREAD=1`). Strata's pool copied each expert's three role slices out of the mmap with
   `memcpy`, after a `madvise(MADV_WILLNEED)` hint. Under memory pressure the kernel throttles or
   drops that readahead, and the copy then takes one major fault per 4 KB page with 64 KB
   read-around, 500 faults per 2 MB expert, each a synchronous NVMe round trip while the kernel also
   reclaims (direct-reclaim stalls were at 1.1 M). A `pread` of the slice is one request, the page
   cache is still used, nothing else changes. Back to back at chunk 32768: 80K 1,471 -> 1,796
   tok/s, 2K prompts 138-238 -> 348-376 tok/s, 80K follow-up 10.4 -> 6.1 s, faults 951 K -> 13.8 K,
   swap-ins 3.2 GB -> 47 MB, NVMe bytes 325 -> 202 GB.

Both GPUs are now busy during a prompt instead of waiting on the pool. Not needed after these:
`MADV_RANDOM`, locking the heap, readahead changes, moving the swap file.

## Upstream 0.1.38, the fused prompt kernels and six open PRs

The first release of this repo sat on 0.1.33, the second on 0.1.37. Upstream 0.1.36 added fused int8
tensor-core kernels for the prompt path's experts (#136): on by default for the Q2_0 pack, opt-in with
`STRATA_PF_FUSED=1` for the native IQ packs. The fused path runs for a prompt chunk of 1,024 tokens or more
whose layer streams all of its non-resident experts, and only for layers whose gate/up and down tensor
types the kernels cover; this GGUF uses exactly those types in all 48 layers. Against MMQ on the same
build: 80K 1,826 -> 1,969-1,994 tok/s, 16K 1,080 -> 1,212-1,240, the 80K follow-up 6.7 -> 5.8 s, decode
unchanged. Upstream's own +23% (#519) was measured with every expert resident in 96 GB of RAM.

0.1.38 (released 2026-10-03) merged PR #385 and brought small prompt gains. Six open PRs were applied on
top: #603 matters most here (it is upstream since 0.1.39). Strata's fast top-k over the selected attention blocks
holds one query's keys in registers and covers 33,792 blocks, about 135K cells, on NVIDIA; a 262,144
context has 65,536 blocks, so every prompt batch and every decode window on the 5090 took the old
six-pass kernel. #603 adds a register-layout kernel with no size limit and the same ids. #547 makes the
prompt path borrow 1.25 GiB fewer expert-cache slots per 32K chunk (6,243 instead of 6,939 here).
#567 keeps the last rendered prompts and tokenises only the text after the shared prefix. #510, #572
and #525 are server-side tool-call fixes. Same bench, 0.1.37 to 0.1.38 with the PRs: decode 110,
2K 373-376, 16K 1,305, 80K 2,094, follow-up 5.5 s.

## What the prompt loan costs, and what did not fix it

The prompt path borrows 6,243 of the 5090's expert-cache slots (9.77 GiB) for its own buffers on every
prompt; the lent experts are streamed from the file during the prompt and copied back afterwards.
Upstream's comment on this says the loan is cheap when the lent experts are "DMA'd from pinned RAM",
which is the 64 GB-and-up case. Here they come from the SSD, so an 80K prompt reads about 100 GB from
NVMe, six times what the expert miss rate alone predicts. Measured on 2026-10-03, nothing in the flag
set moves this:

- `--layer-split 38`: the 4070 then holds every pair of its 10 layers (5,120 of 5,120, zero stage
  misses) but with `--prefill-main` the prompt still streams those layers from the file; unchanged.
- the stock split prefill at split 38: 1,203 tok/s at 80K. The 4070 is about 4x slower per layer than
  the 5090, the stages run in sequence, and a full stage cache cannot lend slots, so the chunk fell
  from 32K to 16K.
- `--ple-inflight 256`: identical. The n-gram table reads are already direct I/O off the critical path.
- `--no-prefill-borrow` forces 2048-token chunks (measured 3x worse earlier); own buffers for a 32K
  chunk would reserve 21.8 GiB of VRAM.
- parking off, to hand its RAM to the page cache: about 2% on fresh prompts, nothing on follow-ups,
  and every conversation switch becomes a full re-read.

## The dual-GPU fork (2026-10-03 to 2026-10-04)

Hardin22's Strata-DualGPU (Strata issue #642) is the same problem on the same class of box: two cards
and 32 GB of RAM. It lets `--resident-experts` run with `--layer-split`: the RAM copy is the complement
of every card's cache, hottest first, page-locked, and a swap-back bug (an evicted expert copied back
from the wrong card's slot) is fixed. Here the copy is 6.9 GiB and the decode hit path never reads
the file. It also pipelines decode: with `--pipeline-windows 2` stage 0 runs window K+1 on tokens from
a teacher-forced MTP chain while stage 1 still verifies window K, with a GDN snapshot (112 MiB on the
5090) to undo K+1 when K's acceptance disagrees. The stages hand off through flags in mapped pinned
memory, commits are queued per stream, the draft round is one graph, and the adaptive tier swaps
asynchronously. On this box: decode 110 -> 170 tok/s median, 117 -> 155 after an 80K prompt, 2K
prompts 373 -> 450-460, the 80K follow-up 5.5 -> 4.4 s, 16K and 80K prompts unchanged (the loan above
is still the floor there). Needle 5/5, parking 8/8, coherence probes and a second decode set clean.

Two things to know about that first fork commit. Its separate reserve for the second card had to stay at
700 MiB: at 300 the 4070's expert cache grew by 175 slots and the MTP draft head no longer fit ("the
draft head does not fit"). The fork's hybrid-CPU pool default (P-cores plus half the E-cores) is
Windows-only; 13 workers set by hand measured the same as the 19-worker default on this box, because
decode misses are 0.5% and served from RAM.

## The fork's second day: each card keeps its own layers' weights

Six more fork commits change the memory picture. A split used to load the dense weights of
all 48 layers on every card; now each card reloads only its own. Under `--prefill-main` that cannot
apply to the 5090, which reads every layer of a prompt, so patch 10 makes CUDA0 keep all 48 and lets the
later cards trim. The 4070 frees 2,419 MiB and holds all 6,144 expert pairs of layers 36-47 (about 5,200
before), the RAM copy shrinks from 6.56 to 4.83 GiB, and the draft head's room is kept out of the last
card's cache, which removes the trap above (700 MiB stays anyway: the 4070 has room to spare). The
CPU expert kernels use AVX-VNNI and gathers on Intel P-cores. Decode 170 -> 173, after an 80K prompt
155 -> 161-175, RAM in use 23.4 -> 20.2 GB, prompts unchanged. Splits 35 and 34 were tried again on
this build: the 4070 then misses 360 to 900 of its pairs, 0.4 GiB of RAM is saved and decode falls to
161-168; 36 stays.

## The loan from locked RAM

On one GPU the resident mode already keeps the lent slots' experts in RAM "as far as RAM allows", so a
prompt streams them from pinned memory. On a layer split both upstream and the fork turn that off (the
copy's budget goes to the experts no card holds). Patch 12 adds `STRATA_RESIDENT_LEND=1`: on a split the
lend region is kept too, from the last slot down (a short prompt borrows only the last slots), with what
RAM is left after the whole complement and the headroom (`STRATA_RESIDENT_HEADROOM_GIB`). The GPU cache
is untouched, so decode does not change; the cost is RAM only.

Locking all 9.77 GiB of it (14.59 GiB with the complement) reads an 80K prompt at 3,089-3,173 tok/s
instead of 2,127 and a 16K one at 2,175 instead of 1,282. But it leaves about 1 GB available, and the
engine's parking admission keeps a 2,560 MiB floor: every park is refused ("skip parking (physical RAM
admission ...)"), so a switch between two chats costs a re-read (5-8 s for 15K and 30K instead of 0.4 s),
and so does every side request a chat app sends between turns. A headroom of 10 GiB (shipped until 2026-10-05, 14 since) locks
10.01 GiB, which covers the loan of a chunk up to about 17K tokens: 2K, 16K, follow-ups and tool-result
steps keep the whole gain, an 80K prompt none (its 32K chunks borrow past the covered part), and
parking works with about 3 GB of conversations before the floor refuses more. The headroom check reads
the available RAM at boot, when the page cache still counts as available: a headroom of 7 still locked
13 GiB. A smaller chunk does not rescue the long prompt: one 16K chunk already reads at about 2,170
tok/s.

## Short reads through the decode windows

A part of the prompt of at most `--short-read` tokens (default 64) is read through the verify windows,
as decode reads tokens; anything longer takes the batched path. The batched path has a fixed cost per
run (it borrows slots, streams the experts the chunk routes to that are not in VRAM, refills), about
1.6 s here on real text, then about 1.1 ms a token; a window costs about 2.2 ms a token and nothing
up front. On the same server, the same conversation and real web text, thresholds of 64 / 256 / 512 /
1024 read 130-160 new tokens in 1.7 / 0.5 / 0.4 / 0.4 s, 400 in 2.1 / 2.1 / 1.0 / 1.0 s, 640-740 in
2.0-2.6 s against 1.4-1.6 s at 1024, and 884 in 2.85 against 3.4 s. The config uses 768. From 1,024
tokens a chunk streams every expert the GPU does not hold, which is the step in the curve that patch 12
flattens. Text built from a small vocabulary routes to few experts and made the batched path look three
times cheaper; `tools/step_times.py` takes a file of real text for that reason.

## Clients that merge a turn's tool calls

The engine continues a conversation from the live session, or from a checkpoint it keeps at each turn
boundary, as long as the new prompt starts with the tokens it holds. Some chat apps store one assistant
message per user turn and send `assistant{tool_calls: [every call so far]}` followed by all the tool
results. The model wrote calls and results step by step, so each new call is rendered in front of the
earlier results, the prompt differs right after the user's message, and every step falls back to that
checkpoint: in one 30-call research turn the log shows `14362 reused` on 19 requests in a row, the
re-read growing from 24K to 134K tokens and from 15 to 51 s per step.

Patch 13 makes the server undo this. A tool call id is `call_<16 hex>_<n>`, the 16 hex digits naming
the response that issued it. `openai_to_messages` splits an assistant message whose calls carry two or
more markers into one assistant message per response, each followed by its results. Text sent with the
calls stays with the first step while the turn is running and becomes a closing assistant message once
the conversation went on; reasoning goes with the last step. Ids of another server, a response's calls
that are not adjacent, or a result of an unknown call leave the message as it was sent. With
`tools/merged_tool_turn.py` every step then reuses the whole conversation and reads only the new
result; with `OLD_IDS=1` each step reuses the first 300 tokens. What still costs a full read: a client
that changes its system prompt between turns (a memory feature that rewrites it does).

## Back on upstream: v0.1.39 with the fork's work as PRs (2026-10-05)

Hardin22 sent the fork's changes upstream as separate PRs: #848 (the RAM copy on a layer split), #859
(pipelined verify windows), #851 (AVX2 Q8_K quantizer), #863 (CPU IQ kernels), #876 / #905 / #910
(the asynchronous expert tier, pipelined decode, fork parity) and #904 (verify-window PDL and graph
branches). This repo now clones upstream Strata at the v0.1.39 tag and applies, in order, those PRs, the
five still-open PRs from before (#547, #567, #510, #572, #525) and our four patches; each patch is one
step of the tested branch, conflict resolutions included, so the series rebuilds that tree byte for byte
(`patches/MANIFEST.sha256`). Two upstream changes mattered: the fork's defaults are opt-in there, so the
config now passes `--trim-stage-weights --pipeline-windows 2 --adapt-async 1`; and 0.1.39 made the #525
rescue of a tool call stranded in an unclosed thinking span opt-in, so the config sets
`"format_fixes": "stranded-call"`. Patch 10 also changed: under `--prefill-main` CUDA0 skips upstream's
stage trim, and a parked conversation is one CUDA0 image (the stage state is copied back from it).

Against the fork build on the same text and config, decode was about 9% faster and each tool step about
0.3 s slower. Two settings then won that back:

- `STRATA_SPLIT_SMALL_OWN=3072` (#340): a read of up to 3,072 tokens keeps 986 of the 5090's cache
  slots instead of borrowing them, so it streams far fewer experts. Tool steps of 1.5K / 2.7K / 5.9K
  tokens went 3.79 / 4.29 / 5.81 -> 3.35 / 3.60 / 5.02 s and 2K prompts 496 -> 572 tok/s; decode fell
  from 193 to 176 (the kept slots are not there for decode). 2,048 tied, 4,096 lost decode (167) for
  nothing. For an agent that spends its time in tool steps this is the better balance.
- `MALLOC_MMAP_THRESHOLD_=1048576 MALLOC_ARENA_MAX=4`: glibc returns big buffers to the kernel instead
  of keeping them in per-thread arenas; about 0.7 GB more available RAM, speed unchanged.

The lend headroom went from 10 to 14 GiB and parking from 4 to 6 GB (8 slots): with less RAM locked a
long conversation always parks, so switching chats or a client's side request never forces a re-read.
Measured and not adopted: `STRATA_PM_SHARE=1` (decode 78), `STRATA_MTP_KV=f16`,
`STRATA_PREFILL_LEND_PCT=60` and `STRATA_PREFILL_HELP=1` (neutral; the helper is inactive under
`--prefill-main`). 4-bit KV was left out on purpose: the KV stays at 8 bits.
