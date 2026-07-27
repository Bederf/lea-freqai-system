import re

log_entries = """2026-07-06 12:10:05,050 - LeahAIV5 - INFO - [ETH/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-06 12:10:05,055 - LeahAIV5 - WARNING - [ETH/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=-0.0132)
2026-07-06 12:10:06,724 - LeahAIV5 - INFO - [SOL/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-06 12:10:06,730 - LeahAIV5 - INFO - [SOL/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-06 12:10:06,738 - LeahAIV5 - WARNING - [SOL/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=-0.0132)
2026-07-06 12:10:08,276 - LeahAIV5 - INFO - [BTC/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-06 12:10:08,283 - LeahAIV5 - INFO - [BTC/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-06 12:10:08,290 - LeahAIV5 - WARNING - [BTC/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=+0.0000)
2026-07-06 12:15:02,913 - LeahAIV5 - INFO - [LINK/USDT] Markov updated: P(E)=0.7177, persistence=1 candles (need ≥3)
2026-07-06 12:15:02,921 - LeahAIV5 - INFO - [LINK/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.7177 vs 0.7, persist=1 vs ≥3
2026-07-06 12:15:02,933 - LeahAIV5 - WARNING - [LINK/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=1) g3=False g4=True g5=False(btc_trend=-0.0128)
2026-07-06 12:15:03,973 - LeahAIV5 - INFO - [ETH/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-06 12:15:03,978 - LeahAIV5 - INFO - [ETH/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-06 12:15:03,986 - LeahAIV5 - WARNING - [ETH/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=-0.0128)
2026-07-06 12:15:05,224 - LeahAIV5 - INFO - [SOL/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-06 12:15:05,229 - LeahAIV5 - INFO - [SOL/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-06 12:15:05,237 - LeahAIV5 - WARNING - [SOL/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=-0.0128)
2026-07-06 12:15:06,397 - LeahAIV5 - INFO - [BTC/USDT] Markov updated: P(E)=0.8760, persistence=1 candles (need ≥3)
2026-07-06 12:15:06,403 - LeahAIV5 - INFO - [BTC/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.8760 vs 0.7, persist=1 vs ≥3
2026-07-06 12:15:06,411 - LeahAIV5 - WARNING - [BTC/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=1) g3=False g4=True g5=False(btc_trend=+0.0000)
2026-07-06 12:20:02,478 - LeahAIV5 - INFO - [LINK/USDT] Markov updated: P(E)=0.0004, persistence=0 candles (need ≥3)
2026-07-06 12:20:02,485 - LeahAIV5 - INFO - [LINK/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0004 vs 0.7, persist=0 vs ≥3
2026-07-06 12:20:02,495 - LeahAIV5 - WARNING - [LINK/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=-0.0107)
2026-07-06 12:20:04,137 - LeahAIV5 - INFO - [ETH/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-06 12:20:04,145 - LeahAIV5 - INFO - [ETH/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-06 12:20:04,156 - LeahAIV5 - WARNING - [ETH/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=-0.0107)
2026-07-06 12:20:05,300 - LeahAIV5 - INFO - [SOL/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-06 12:20:05,312 - LeahAIV5 - INFO - [SOL/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-06 12:20:05,319 - LeahAIV5 - WARNING - [SOL/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=True g4=True g5=False(btc_trend=-0.0107)
2026-07-06 12:20:07,259 - LeahAIV5 - INFO - [BTC/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-06 12:20:07,266 - LeahAIV5 - INFO - [BTC/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-06 12:20:07,276 - LeahAIV5 - WARNING - [BTC/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=+0.0000)
2026-07-06 12:25:02,557 - LeahAIV5 - INFO - [LINK/USDT] Markov updated: P(E)=0.1921, persistence=0 candles (need ≥3)
2026-07-06 12:25:02,569 - LeahAIV5 - INFO - [LINK/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.1921 vs 0.7, persist=0 vs ≥3
2026-07-06 12:25:02,592 - LeahAIV5 - WARNING - [LINK/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=-0.0113)
2026-07-06 12:25:04,029 - LeahAIV5 - INFO - [ETH/USDT] Markov updated: P(E)=0.5784, persistence=0 candles (need ≥3)
2026-07-06 12:25:04,036 - LeahAIV5 - INFO - [ETH/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.5784 vs 0.7, persist=0 vs ≥3
2026-07-06 12:25:04,044 - LeahAIV5 - WARNING - [ETH/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=-0.0113)
2026-07-06 12:25:05,556 - LeahAIV5 - INFO - [SOL/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-06 12:25:05,562 - LeahAIV5 - INFO - [SOL/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-06 12:25:05,569 - LeahAIV5 - WARNING - [SOL/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=-0.0113)
2026-07-06 12:25:07,481 - LeahAIV5 - INFO - [BTC/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-06 12:25:07,490 - LeahAIV5 - INFO - [BTC/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-06 12:25:07,498 - LeahAIV5 - WARNING - [BTC/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=+0.0000)
2026-07-06 12:30:02,389 - LeahAIV5 - INFO - [LINK/USDT] Markov updated: P(E)=0.8159, persistence=1 candles (need ≥3)
2026-07-06 12:30:02,395 - LeahAIV5 - INFO - [LINK/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.8159 vs 0.7, persist=1 vs ≥3
2026-07-06 12:30:02,407 - LeahAIV5 - WARNING - [LINK/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=1) g3=False g4=True g5=False(btc_trend=-0.0100)
2026-07-06 12:30:03,480 - LeahAIV5 - INFO - [ETH/USDT] Markov updated: P(E)=0.8881, persistence=1 candles (need ≥3)
2026-07-06 12:30:03,492 - LeahAIV5 - INFO - [ETH/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.8881 vs 0.7, persist=1 vs ≥3
2026-07-06 12:30:03,507 - LeahAIV5 - WARNING - [ETH/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=1) g3=False g4=True g5=False(btc_trend=-0.0100)
2026-07-06 12:30:04,912 - LeahAIV5 - INFO - [SOL/USDT] Markov updated: P(E)=0.0027, persistence=0 candles (need ≥3)
2026-07-06 12:30:04,920 - LeahAIV5 - INFO - [SOL/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0027 vs 0.7, persist=0 vs ≥3
2026-07-06 12:30:04,929 - LeahAIV5 - WARNING - [SOL/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=-0.0100)
2026-07-06 12:30:07,137 - LeahAIV5 - INFO - [BTC/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-06 12:30:07,146 - LeahAIV5 - INFO - [BTC/USDT] v5 gates: GARCH=-0.4724 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-06 12:30:07,154 - LeahAIV5 - WARNING - [BTC/USDT] entry check: g1=False(garch=-0.4724) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=+0.0000)"""

gate_lines = [l for l in log_entries.strip().split('\n') if 'v5 gates:' in l]
seen = set()
rows = []
for line in gate_lines:
    m = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),', line)
    ts = m.group(1) if m else '?'
    pair_m = re.search(r'\[(\S+)\]', line)
    pair = pair_m.group(1) if pair_m else '?'
    garch_m = re.search(r'GARCH=([-\d.]+)', line)
    garch = garch_m.group(1) if garch_m else '?'
    pe_m = re.search(r'P\(E\)=([-\d.]+)', line)
    pe = pe_m.group(1) if pe_m else '?'
    persist_m = re.search(r'persist=(\d+)', line)
    persist = persist_m.group(1) if persist_m else '?'
    key = (ts, pair)
    if key in seen:
        continue
    seen.add(key)
    rows.append(f"| {ts} | [{pair}] Markov:P(E)={pe} persist={persist} | GARCH={garch} | g1=False(garch={garch}) g2=False(persist={persist})")

count = len(rows)
last_ts = rows[-1].split('|')[1].strip() if rows else 'N/A'
output = '\n'.join(rows)
print(f"COUNT={count}")
print(f"LAST_TS={last_ts}")
print("---ROWS---")
print(output)
