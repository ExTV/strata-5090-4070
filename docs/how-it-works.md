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
decode-hot pairs of layers 0-35 get evicted and decode after a big prompt fell to 28 tok/s).

## Conversation parking with a layer split

Strata parks a conversation's state in RAM (`--conversation-cache-mib`) so that switching between
chats restores it instead of re-reading it, but refuses the option with `--layer-split`. With
`--prefill-main` the whole state exists on CUDA0 right after any prompt, so the port parks CUDA0's
session (after syncing the stage's layers into it) and, on restore, copies the stage's layers back
to CUDA1. Two conversations of 30K and 15K alternating for four rounds: every answer correct,
switches 0.6-1.2 s. A snapshot is 0.8-1.7 GB per 30K tokens; the budget is 6 GB / 4 slots, which
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
2. **`pread` instead of page faults** (`patches/03-pread-expert-blobs.patch`, on with
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
