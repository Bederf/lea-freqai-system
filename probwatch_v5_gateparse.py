import re

log_entries = """2026-07-07 15:19:33,693 - freqtrade.plugins.pairlistmanager - INFO - Whitelist with 4 pairs: ['LINK/USDT', 'ETH/USDT', 'SOL/USDT', 'BTC/USDT']
2026-07-07 15:20:02,385 - LeahAIV5 - INFO - [LINK/USDT] Markov updated: P(E)=0.8501, persistence=3 candles (need ≥3)
2026-07-07 15:20:02,395 - LeahAIV5 - INFO - [LINK/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.8501 vs 0.7, persist=3 vs ≥3
2026-07-07 15:20:02,413 - LeahAIV5 - WARNING - [LINK/USDT] ENTRY TRIGGERED: g1=True g2=True g3=True g4=True g5=True
2026-07-07 15:20:03,638 - LeahAIV5 - INFO - [ETH/USDT] Markov updated: P(E)=0.0430, persistence=0 candles (need ≥3)
2026-07-07 15:20:03,649 - LeahAIV5 - INFO - [ETH/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.0430 vs 0.7, persist=0 vs ≥3
2026-07-07 15:20:03,660 - LeahAIV5 - WARNING - [ETH/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=0) g3=True g4=True g5=True(btc_trend=+0.0049)
2026-07-07 15:20:05,310 - LeahAIV5 - INFO - [SOL/USDT] Markov updated: P(E)=0.0006, persistence=0 candles (need ≥3)
2026-07-07 15:20:05,338 - LeahAIV5 - INFO - [SOL/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.0006 vs 0.7, persist=0 vs ≥3
2026-07-07 15:20:05,350 - LeahAIV5 - WARNING - [SOL/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=0) g3=True g4=True g5=True(btc_trend=+0.0049)
2026-07-07 15:20:06,732 - LeahAIV5 - INFO - [BTC/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-07 15:20:06,746 - LeahAIV5 - INFO - [BTC/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-07 15:20:06,758 - LeahAIV5 - WARNING - [BTC/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=0) g3=True g4=True g5=False(btc_trend=+0.0000)
2026-07-07 15:20:07,126 - LeahAIV5 - INFO - [LINK/USDT] confirm APPROVED: garch=0.6907 persist=3 close=7.9180 btc_trend=+0.0037 | tag=garch_0.691_pe_0.85_dur_3
2026-07-07 15:25:02,212 - LeahAIV5 - INFO - [LINK/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-07 15:25:02,220 - LeahAIV5 - INFO - [LINK/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-07 15:25:02,227 - LeahAIV5 - WARNING - [LINK/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=0) g3=True g4=True g5=True(btc_trend=+0.0069)
2026-07-07 15:25:03,422 - LeahAIV5 - INFO - [ETH/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-07 15:25:03,443 - LeahAIV5 - INFO - [ETH/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-07 15:25:03,451 - LeahAIV5 - WARNING - [ETH/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=0) g3=True g4=True g5=True(btc_trend=+0.0069)
2026-07-07 15:25:04,549 - LeahAIV5 - INFO - [SOL/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-07 15:25:04,555 - LeahAIV5 - INFO - [SOL/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-07 15:25:04,563 - LeahAIV5 - WARNING - [SOL/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=0) g3=True g4=True g5=True(btc_trend=+0.0069)
2026-07-07 15:25:05,701 - LeahAIV5 - INFO - [BTC/USDT] Markov updated: P(E)=0.0000, persistence=0 candles (need ≥3)
2026-07-07 15:25:05,707 - LeahAIV5 - INFO - [BTC/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.0000 vs 0.7, persist=0 vs ≥3
2026-07-07 15:25:05,715 - LeahAIV5 - WARNING - [BTC/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=0) g3=True g4=True g5=False(btc_trend=+0.0000)
2026-07-07 15:30:02,451 - LeahAIV5 - INFO - [LINK/USDT] Markov updated: P(E)=0.6516, persistence=0 candles (need ≥3)
2026-07-07 15:30:02,464 - LeahAIV5 - INFO - [LINK/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.6516 vs 0.7, persist=0 vs ≥3
2026-07-07 15:30:02,474 - LeahAIV5 - WARNING - [LINK/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=0) g3=True g4=True g5=True(btc_trend=+0.0067)
2026-07-07 15:30:03,747 - LeahAIV5 - INFO - [ETH/USDT] Markov updated: P(E)=0.8416, persistence=1 candles (need ≥3)
2026-07-07 15:30:03,752 - LeahAIV5 - INFO - [ETH/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.8416 vs 0.7, persist=1 vs ≥3
2026-07-07 15:30:03,758 - LeahAIV5 - WARNING - [ETH/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=1) g3=True g4=True g5=True(btc_trend=+0.0067)
2026-07-07 15:30:05,049 - LeahAIV5 - INFO - [SOL/USDT] Markov updated: P(E)=0.0230, persistence=0 candles (need ≥3)
2026-07-07 15:30:05,065 - LeahAIV5 - INFO - [SOL/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.0230 vs 0.7, persist=0 vs ≥3
2026-07-07 15:30:05,073 - LeahAIV5 - WARNING - [SOL/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=0) g3=True g4=True g5=True(btc_trend=+0.0067)
2026-07-07 15:30:06,245 - LeahAIV5 - INFO - [BTC/USDT] Markov updated: P(E)=0.8646, persistence=1 candles (need ≥3)
2026-07-07 15:30:06,253 - LeahAIV5 - INFO - [BTC/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.8646 vs 0.7, persist=1 vs ≥3
2026-07-07 15:30:06,267 - LeahAIV5 - WARNING - [BTC/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=1) g3=True g4=True g5=False(btc_trend=+0.0000)
2026-07-07 15:35:02,562 - LeahAIV5 - INFO - [LINK/USDT] Markov updated: P(E)=0.8962, persistence=1 candles (need ≥3)
2026-07-07 15:35:02,579 - LeahAIV5 - INFO - [LINK/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.8962 vs 0.7, persist=1 vs ≥3
2026-07-07 15:35:02,589 - LeahAIV5 - WARNING - [LINK/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=1) g3=True g4=True g5=True(btc_trend=+0.0066)
2026-07-07 15:35:03,729 - LeahAIV5 - INFO - [ETH/USDT] Markov updated: P(E)=0.9308, persistence=2 candles (need ≥3)
2026-07-07 15:35:03,738 - LeahAIV5 - INFO - [ETH/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.9308 vs 0.7, persist=2 vs ≥3
2026-07-07 15:35:03,745 - LeahAIV5 - WARNING - [ETH/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=2) g3=True g4=True g5=True(btc_trend=+0.0066)
2026-07-07 15:35:04,633 - LeahAIV5 - INFO - [SOL/USDT] Markov updated: P(E)=0.8520, persistence=1 candles (need ≥3)
2026-07-07 15:35:04,641 - LeahAIV5 - INFO - [SOL/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.8520 vs 0.7, persist=1 vs ≥3
2026-07-07 15:35:04,648 - LeahAIV5 - WARNING - [SOL/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=1) g3=True g4=True g5=True(btc_trend=+0.0066)
2026-07-07 15:35:05,655 - LeahAIV5 - INFO - [BTC/USDT] Markov updated: P(E)=0.9326, persistence=2 candles (need ≥3)
2026-07-07 15:35:05,665 - LeahAIV5 - INFO - [BTC/USDT] v5 gates: GARCH=0.6907 vs 0.05, P(E)=0.9326 vs 0.7, persist=2 vs ≥3
2026-07-07 15:35:05,675 - LeahAIV5 - WARNING - [BTC/USDT] entry check: g1=True(garch=0.6907) g2=False(persist=2) g3=True g4=True g5=False(btc_trend=+0.0000)"""

gate_lines = []
for line in log_entries.strip().split('\n'):
    m = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - LeahAIV5 - (INFO|WARNING) - \[(\S+)\] (.+)$', line)
    if m:
        ts = m.group(1)
        level = m.group(2)
        pair = m.group(3)
        msg = m.group(4)
        gate_lines.append(f"{ts} | {pair} | {level} | {msg}")

last_ts = "2026-07-07T15:37:31+00:00"
output = "LAST_TS=" + last_ts + "\n" + "\n".join(gate_lines)
print(output)
