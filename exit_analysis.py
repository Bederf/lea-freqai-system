#!/usr/bin/env python3
import sqlite3

print("=== EXIT REASON DISTRIBUTION (LEA) ===")
conn = sqlite3.connect('/freqtrade/user_data/tradesv3_lea.sqlite')
exit_dist = conn.execute(
    "SELECT exit_reason, COUNT(*) as cnt, AVG(realized_profit) as avg_profit, "
    "SUM(realized_profit) as total_profit FROM trades WHERE is_open=0 AND exit_reason "
    "IS NOT NULL GROUP BY exit_reason ORDER BY cnt DESC"
).fetchall()
conn.close()

print(f"{'Exit Reason':<25} | {'Count':>5} | {'Avg PnL':>10} | {'Total':>10}")
print("-" * 60)
for row in exit_dist:
    print(f"{str(row[0]):<25} | {row[1]:>5} | {row[2]:>+10.4f} | {row[3]:>+10.4f}")

print("\n=== LOSS SIZE DISTRIBUTION ===")
conn = sqlite3.connect('/freqtrade/user_data/tradesv3_lea.sqlite')
losses = conn.execute(
    "SELECT CASE WHEN realized_profit < -1.0 THEN 'gt_1_loss' "
    "WHEN realized_profit < -0.5 THEN '0.5_to_1_loss' "
    "WHEN realized_profit < -0.2 THEN '0.2_to_0.5_loss' "
    "WHEN realized_profit < -0.1 THEN '0.1_to_0.2_loss' "
    "WHEN realized_profit < 0 THEN '0_to_0.1_loss' ELSE 'winners' END as bucket, "
    "COUNT(*) as cnt FROM trades WHERE is_open=0 GROUP BY bucket ORDER BY bucket"
).fetchall()
conn.close()
for row in losses:
    print(f"{row[0]}: {row[1]} trades")

print("\n=== STOPLOSS HIT ANALYSIS ===")
conn = sqlite3.connect('/freqtrade/user_data/tradesv3_lea.sqlite')
sl_hits = conn.execute(
    "SELECT SUM(CASE WHEN exit_reason='stoploss' THEN 1 ELSE 0 END) as sl_count, "
    "SUM(CASE WHEN exit_reason='stoploss' THEN realized_profit ELSE 0 END) as sl_total, "
    "COUNT(*) as total_trades FROM trades WHERE is_open=0"
).fetchone()
conn.close()
print(f"Stop-loss exits: {sl_hits[0]}")
print(f"Stop-loss total PnL: {sl_hits[1]:.4f}")
print(f"Total trades: {sl_hits[2]}")

print("\n=== BOTTOM 10 LOSSES ===")
conn = sqlite3.connect('/freqtrade/user_data/tradesv3_lea.sqlite')
worst = conn.execute(
    "SELECT pair, realized_profit, exit_reason, open_date FROM trades WHERE is_open=0 "
    "ORDER BY realized_profit ASC LIMIT 10"
).fetchall()
conn.close()
for row in worst:
    print(f"{row[0]}: {row[1]:+.4f} ({row[2]}) @ {row[3]}")