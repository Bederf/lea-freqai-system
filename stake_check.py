#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect('/freqtrade/user_data/tradesv3_lea.sqlite')
rows = conn.execute("""
    SELECT stake_amount, open_rate, stop_loss_pct,
           realized_profit, exit_reason
    FROM trades
    WHERE is_open=0 AND stake_amount IS NOT NULL
    LIMIT 20
""").fetchall()
conn.close()
print("stake_amt | open_rate | stop_loss_pct | profit | exit_reason")
print("-"*70)
for r in rows:
    print(f"{r[0]:>9.2f} | {r[1]:>10.6f} | {r[2]:>12.4f} | {r[3]:>+8.4f} | {r[4]}")

conn = sqlite3.connect('/freqtrade/user_data/tradesv3_lea.sqlite')
avg_stake = conn.execute("SELECT AVG(stake_amount) FROM trades WHERE is_open=0").fetchone()[0]
avg_profit = conn.execute("SELECT AVG(realized_profit) FROM trades WHERE is_open=0").fetchone()[0]
avg_loss_abs = conn.execute("SELECT AVG(realized_profit) FROM trades WHERE is_open=0 AND realized_profit < 0").fetchone()[0]
wins = conn.execute("SELECT AVG(realized_profit) FROM trades WHERE is_open=0 AND realized_profit > 0").fetchone()[0]
conn.close()
print(f"\nAvg stake: {avg_stake:.2f} USDT")
print(f"Avg winner: +{wins:.4f} USDT")
print(f"Avg loser: {avg_loss_abs:.4f} USDT")
print(f"Loss as % of stake: {abs(avg_loss_abs)/avg_stake*100:.1f}%")
print(f"Win as % of stake: {wins/avg_stake*100:.1f}%")