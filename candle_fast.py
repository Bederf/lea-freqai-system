#!/usr/bin/env python3
"""Fast candle analysis - sample trades and check pattern"""
import sqlite3
import pandas as pd
import glob
import os

print("=== CANDLE-BY-CANDLE PnL ANALYSIS ===\n")

conn = sqlite3.connect('/freqtrade/user_data/tradesv3_lea.sqlite')
trades = pd.read_sql(
    "SELECT id, pair, open_date, close_date, open_rate, realized_profit, exit_reason "
    "FROM trades WHERE is_open=0 ORDER BY open_date DESC LIMIT 50",
    conn
)
conn.close()

print(f"Sampled {len(trades)} trades\n")

# Pre-load all USDT pair data into memory
data_dir = '/freqtrade/user_data/data/binance'
cache = {}
pairs = trades['pair'].unique()
for pair in pairs:
    pair_file = pair.replace('/', '_')
    pattern = f'{data_dir}/{pair_file}-5m.feather'
    files = glob.glob(pattern)
    if files:
        try:
            df = pd.read_feather(files[0])
            cache[pair] = df
        except:
            pass

print(f"Cached {len(cache)} pairs\n")

def get_candle_after_entry(pair, open_date, candle_idx):
    if pair not in cache:
        return None
    df = cache[pair]
    open_dt = pd.to_datetime(open_date).tz_localize('UTC')
    df_valid = df[df['date'] >= open_dt]
    if len(df_valid) <= candle_idx:
        return None
    return df_valid.iloc[candle_idx]

# Analyze candle 0-10 PnL
print("="*70)
print("Candle | Count |  Avg PnL  | StdDev  |   Min  |   Max")
print("-"*70)

candles = {}
for i in range(11):
    pnls = []
    for idx, trade in trades.iterrows():
        candle = get_candle_after_entry(trade['pair'], trade['open_date'], i)
        if candle is not None:
            entry_rate = trade['open_rate']
            pnl = (candle['close'] - entry_rate) / entry_rate * 100
            pnls.append(pnl)
    if pnls:
        avg = sum(pnls) / len(pnls)
        std = (sum((p - avg)**2 for p in pnls) / len(pnls)) ** 0.5
        min_p = min(pnls)
        max_p = max(pnls)
        candles[i] = {'count': len(pnls), 'avg': avg, 'std': std, 'min': min_p, 'max': max_p}
        print(f"  {i:<4} | {len(pnls):>5} | {avg:>+8.3f}% | {std:>7.3f} | {min_p:>+7.3f}% | {max_p:>+7.3f}%")

# Max PnL reached analysis
print("\n" + "="*70)
print("MAX PNL REACHED DURING TRADE")
print("="*70)

results = []
for idx, trade in trades.iterrows():
    pair = trade['pair']
    if pair not in cache:
        continue
    df = cache[pair]
    open_dt = pd.to_datetime(trade['open_date']).tz_localize('UTC')
    df_valid = df[df['date'] >= open_dt].head(40)

    entry_rate = trade['open_rate']
    max_pnl = 0
    max_pnl_candle = 0

    for c_i, (_, candle) in enumerate(df_valid.iterrows()):
        pnl = (candle['close'] - entry_rate) / entry_rate * 100
        if pnl > max_pnl:
            max_pnl = pnl
            max_pnl_candle = c_i + 1

    results.append({
        'pair': pair,
        'realized_profit': trade['realized_profit'],
        'exit_reason': trade['exit_reason'],
        'max_pnl': max_pnl,
        'max_pnl_candle': max_pnl_candle
    })

rdf = pd.DataFrame(results)
print(f"\nMax PnL reached distribution:")
buckets = [(0,1,"0-1%"), (1,2,"1-2%"), (2,3,"2-3%"), (3,5,"3-5%"), (5,999,">5%")]
for lo, hi, label in buckets:
    cnt = len(rdf[(rdf['max_pnl'] >= lo) & (rdf['max_pnl'] < hi)])
    pct = cnt / len(rdf) * 100 if len(rdf) > 0 else 0
    print(f"  {label:>8}: {cnt:>3} ({pct:5.1f}%)")

print(f"\nWhen does max PnL occur?")
buckets2 = [(1,3,"Candle 1-3"), (3,6,"Candle 4-6"), (6,12,"Candle 7-12"), (12,999,">12")]
for lo, hi, label in buckets2:
    cnt = len(rdf[(rdf['max_pnl_candle'] >= lo) & (rdf['max_pnl_candle'] < hi)])
    pct = cnt / len(rdf) * 100 if len(rdf) > 0 else 0
    print(f"  {label:>12}: {cnt:>3} ({pct:5.1f}%)")

print(f"\nAvg candle of max PnL: {rdf['max_pnl_candle'].mean():.1f}")

# Trailing stop analysis
print("\n" + "="*70)
print("TRAILING STOP ANALYSIS")
print("="*70)
trailing = rdf[rdf['exit_reason'] == 'trailing_stop_loss']
print(f"Trailing stop exits: {len(trailing)}")
if len(trailing) > 0:
    print(f"  Avg max PnL reached: {trailing['max_pnl'].mean():.2f}%")
    print(f"  Avg candle of max: {trailing['max_pnl_candle'].mean():.1f}")
    print(f"\n  Max PnL distribution for trailing stops:")
    for lo, hi, label in [(0,1,"0-1%"), (1,2,"1-2%"), (2,3,"2-3%"), (3,999,">3%")]:
        cnt = len(trailing[(trailing['max_pnl'] >= lo) & (trailing['max_pnl'] < hi)])
        pct = cnt / len(trailing) * 100
        print(f"    {label:>8}: {cnt:>3} ({pct:5.1f}%)")

# Trades that went positive but still lost
print("\n" + "="*70)
print("TRADES THAT WENT POSITIVE BUT STILL LOST")
print("="*70)
went_pos = rdf[rdf['max_pnl'] > 0]
still_lost = went_pos[went_pos['realized_profit'] < 0]
print(f"Trades that went positive: {len(went_pos)}")
print(f"Of those, still lost: {len(still_lost)} ({len(still_lost)/len(went_pos)*100:.1f}%)")
if len(still_lost) > 0:
    print(f"Average max PnL reached: {still_lost['max_pnl'].mean():.2f}%")
    print(f"Where did they peak?")
    for lo, hi, label in [(1,3,"Candle 1-3"), (3,6,"Candle 4-6"), (6,999,">6")]:
        cnt = len(still_lost[(still_lost['max_pnl_candle'] >= lo) & (still_lost['max_pnl_candle'] < hi)])
        print(f"  {label:>12}: {cnt:>3}")