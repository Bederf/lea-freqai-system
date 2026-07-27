import re, subprocess, json
out = subprocess.check_output(
    ["docker", "logs", "freqtrade-lea-new"], stderr=subprocess.STDOUT, text=True, timeout=30
)
lines = [l for l in out.splitlines() if "v4.4 override" in l]

# Take last cycle per pair (latest log line per pair)
last_cycle = {}
for l in lines:
    m = re.search(r"\[([A-Z]+/USDT)\].*?mean=([\d.]+).*?std=([\d.]+).*?%>55=(\d+)/(\d+)", l)
    if not m:
        continue
    pair = m.group(1)
    last_cycle[pair] = {
        "mean": float(m.group(2)),
        "std": float(m.group(3)),
        "pct_above_55": round(100 * int(m.group(4)) / int(m.group(5)), 2),
    }

# Rolling stats over last 20 cycles per pair
import collections
buckets = collections.defaultdict(list)
cycle_re = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}).*?\[([A-Z]+/USDT)\].*?mean=([\d.]+).*?std=([\d.]+).*?%>55=(\d+)/(\d+)"
)
for l in lines:
    m = cycle_re.search(l)
    if not m:
        continue
    buckets[m.group(2)].append(
        {
            "ts": m.group(1),
            "mean": float(m.group(3)),
            "std": float(m.group(4)),
            "hi": int(m.group(5)),
            "n": int(m.group(6)),
        }
    )

result = {"last_cycle": last_cycle, "rolling_20": {}}
for p in ["BTC/USDT", "ETH/USDT", "SOL/USDT", "LINK/USDT"]:
    recent = buckets[p][-20:]
    if not recent:
        continue
    means = [r["mean"] for r in recent]
    hi_sum = sum(r["hi"] for r in recent)
    n_sum = sum(r["n"] for r in recent)
    result["rolling_20"][p] = {
        "runs": len(recent),
        "mean_of_means": round(sum(means) / len(means), 4),
        "latest": recent[-1]["mean"],
        "pct55_rolling": round(100 * hi_sum / n_sum, 2),
    }

print(json.dumps(result, indent=2))