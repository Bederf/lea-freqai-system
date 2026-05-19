#!/usr/bin/env python3
"""Fast 15m SMA filter test"""
import sqlite3
import pandas as pd
import glob

def get_15m_regime(pair, open_date):
    pair_file = pair.replace('/', '_')
    pattern = f'/freqtrade/user_data/data/binance/{pair_file}-15m.feather'
    files = glob.glob(pattern)
    if not files:
        return -1
    try:
        df = pd.read_feather(files[0])
        if len(df) < 60:
            return -1
        df['sma20'] = df['close'].rolling(20).mean()
        df['sma50'] = df['close'].rolling(50).mean()
        df['regime'] = (df['sma20'] > df['sma50']).astype(int)
        open_dt = pd.to_datetime(open_date).tz_localize('UTC')
        valid = df[df['date'] <= open_dt]
        return int(valid.iloc[-1]['regime']) if len(valid) > 0 else -1
    except:
        return -1

conn = sqlite3.connect('/freqtrade/user_data/tradesv3_lea.sqlite')
trades = pd.read_sql(
    "SELECT pair, open_date, realized_profit, exit_reason FROM trades "
    "WHERE is_open=0 ORDER BY open_date DESC LIMIT 100",
    conn
)
conn.close()

print(f"Testing {len(trades)} trades...")

# Cache 15m data for unique pairs
pairs = trades['pair'].unique()
cache = {}
for pair in pairs:
    pair_file = pair.replace('/', '_')
    pattern = f'/freqtrade/user_data/data/binance/{pair_file}-15m.feather'
    files = glob.glob(pattern)
    if files:
        try:
            df = pd.read_feather(files[0])
            df['sma20'] = df['close'].rolling(20).mean()
            df['sma50'] = df['close'].rolling(50).mean()
            df['regime'] = (df['sma20'] > df['sma50']).astype(int)
            cache[pair] = df
        except:
            pass

print(f"Cached {len(cache)} pairs")

def get_regime(pair, open_date):
    if pair not in cache:
        return -1
    try:
        open_dt = pd.to_datetime(open_date).tz_localize('UTC')
        valid = cache[pair][cache[pair]['date'] <= open_dt]
        return int(valid.iloc[-1]['regime']) if len(valid) > 0 else -1
    except:
        return -1

# Label regimes
regimes = [get_regime(row['pair'], row['open_date']) for _, row in trades.iterrows()]
trades['regime_15m'] = regimes

known = trades[trades['regime_15m'] >= 0]
up = known[known['regime_15m'] == 1]
down = known[known['regime_15m'] == 0]

print(f"\n15m Uptrend: {len(up)} trades")
print(f"15m Downtrend: {len(down)} trades")

def stats(group):
    if len(group) == 0:
        return
    wr = (group['realized_profit'] > 0).mean() * 100
    winners = group[group['realized_profit'] > 0]['realized_profit']
    losers = group[group['realized_profit'] < 0]['realized_profit']
    avg_w = winners.mean() if len(winners) > 0 else 0
    avg_l = losers.mean() if len(losers) > 0 else 0
    exp = (wr/100 * avg_w) + ((100-wr)/100 * avg_l)
    print(f"  Win rate: {wr:.1f}% | Avg W: +{avg_w:.4f} | Avg L: {avg_l:.4f} | Expectancy: {exp:+.4f} | Total: {group['realized_profit'].sum():+.4f}")

print("\n15m Uptrend trades:")
stats(up)
print("\n15m Downtrend trades:")
stats(down)

print(f"\n{'='*60}")
print("DECISION")
print(f"{'='*60}")
all_wr = (known['realized_profit'] > 0).mean() * 100
up_wr = (up['realized_profit'] > 0).mean() * 100
print(f"Current win rate: {all_wr:.1f}%")
print(f"15m-up filtered win rate: {up_wr:.1f}%")
print(f"Win rate improvement: {up_wr - all_wr:+.1f}%")
print(f"Trade reduction: {(1 - len(up)/len(known))*100:.1f}%")

if up_wr > all_wr and len(up) > 10:
    print(f"\n✓ 15m filter IMPROVES win rate - recommend applying")