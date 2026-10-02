"""one-line JSON snapshot of the counters the A/B diffs: major faults, swap-ins, direct-reclaim scans and allocation
stalls, NVMe sectors read (nvme* whole devices only), GPU clocks/temps/power. STRATA_URL is not needed here."""
import json, subprocess
vm = dict(l.split() for l in open("/proc/vmstat"))
rd = sum(int(l.split()[5]) for l in open("/proc/diskstats") if l.split()[2].startswith("nvme") and "p" not in l.split()[2])
smi = subprocess.run(["nvidia-smi", "--query-gpu=clocks.sm,clocks.mem,temperature.gpu,power.draw", "--format=csv,noheader,nounits"],
                     capture_output=True, text=True).stdout.split("\n")
print(json.dumps({"pgmajfault": int(vm["pgmajfault"]), "pswpin": int(vm["pswpin"]), "pgscan_direct": int(vm["pgscan_direct"]),
                  "allocstall": int(vm["allocstall_normal"]) + int(vm["allocstall_movable"]), "nvme_read_MB": rd * 512 // 1048576,
                  "gpu": [s.strip() for s in smi if s.strip()]}))
