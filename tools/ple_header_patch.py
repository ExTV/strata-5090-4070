#!/usr/bin/env python3
"""Makes Unsloth's standalone PLE n-gram table (engram/Qwen3.8-Flash-Next-engram-Q8_0.gguf_file) loadable through
--ple-gguf on Strata v0.2.1.  The file carries split.no / split.count / split.tensors.count and no
general.architecture, so v0.2.1 appends it to the model's dense shards and stops with "additional shard must match
the architecture-validated first shard's split metadata".  The three split keys (82 bytes at offset 24) are
replaced in place by general.architecture=strata-ple and two padding keys of the same total length, so nothing
after them moves.  The original bytes are checked first and saved next to the file; --restore puts them back.

    tools/ple_header_patch.py FILE [--restore]
"""
import sys
OFF = 24
ORIG = bytes.fromhex("080000000000000073706c69742e6e6f0200000000000b0000000000000073706c69742e636f756e7402000000"
                     "0100130000000000000073706c69742e74656e736f72732e636f756e7405000000c8040000")
NEW = bytes.fromhex("140000000000000067656e6572616c2e617263686974656374757265080000000a000000000000007374726174"
                    "612d706c650300000000000000706430000000000003000000000000007064310000000000")
assert len(ORIG) == len(NEW) == 82
path, restore = sys.argv[1], "--restore" in sys.argv[2:]
want, put = (NEW, ORIG) if restore else (ORIG, NEW)
with open(path, "r+b") as f:
    head = f.read(OFF + len(ORIG))
    if head[:4] != b"GGUF":
        sys.exit(f"{path}: not a GGUF file")
    have = head[OFF:]
    if have == put:
        sys.exit(0)                      # already done
    if have != want:
        sys.exit(f"{path}: the header is not the one this tool knows (another table or revision); nothing changed")
    if not restore:
        with open(path + ".header-orig.bin", "wb") as b:
            b.write(head)
    f.seek(OFF)
    f.write(put)
print(f"{path}: header {'restored' if restore else 'patched'}")
