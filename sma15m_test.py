#!/usr/bin/env python3
"""
15m SMA Confirmation Test
Tests if adding 15m trend filter improves trade performance
"""
import sqlite3
import pandas as pd
import glob

def compute_sma(series, period):
    return series.rolling(period).mean()

def get_15m_regime_at_entry(pair, open_date, data_dir='/freqtrade/user_data/data/binance'):
    """Get 15m SMA trend at entry time"""
    pair_file = pair.replace('/', '_')
    # Try 15m data first, fall back to 1h if needed
    pattern_15m = f'{data_dir}/{pair_file}-15m.feather'
    pattern_1h = f'{data_dir}/{pair_file}-1h.feather'

    pattern = pattern_15m if glob.glob(pattern_15m) else pattern_1h
    files = glob.glob(pattern)

    if not files:
        return -1  # unknown

    try:
        df = pd.read_feather(files[0])
        if df is None or len(df) < 60:
            return -1

        # Compute SMAs
        df['sma_20'] = compute_sma(df['close'], 20)
        df['sma_50'] = compute_sma(df['close'], 50)
        df['regime_15m'] = (df['sma_20'] > df['sma_50']).astype(int)

        open_dt = pd.to_datetime(open_date).tz_localize('UTC')
        df_valid = df[df['date'] <= open_dt]

        if len(df_valid) > 0:
            return int(df_valid.iloc[-1]['regime_15m'])
        return -1
    except Exception as e:
        return -1

print("="*70)
print("15m SMA CONFIRMATION BACKTEST")
print("="*70)

conn = sqlite3.connect('/freqtrade/user_data/tradesv3_lea.sqlite')
trades = pd.read_sql(
    "SELECT id, pair, open_date, close_date, open_rate, close_rate, "
    "realized_profit, exit_reason FROM trades WHERE is_open=0 ORDER BY open_date DESC",
    conn
)
conn.close()

print(f"\nTotal closed trades: {len(trades)}")

# Label each trade with 15m regime at entry
print("Labeling 15m regime at entry...")
regimes = []
for idx, trade in trades.iterrows():
    regime = get_15m_regime_at_entry(trade['pair'], trade['open_date'])
    regimes.append(regime)

trades = trades.copy()
trades['regime_15m'] = regimes

known = trades[trades['regime_15m'] >= 0]
unknown = len(trades) - len(known)
print(f"15m regime labeled: {len(known)} trades, {unknown} unknown")

# Split by 15m regime
regime_up = known[known['regime_15m'] == 1]
regime_down = known[known['regime_15m'] == 0]

print(f"\n15m Uptrend at entry: {len(regime_up)} trades")
print(f"15m Downtrend at entry: {len(regime_down)} trades")

def analyze_group(group, label):
    if len(group) == 0:
        return
    wins = group[group['realized_profit'] > 0]
    losses = group[group['realized_profit'] < 0]
    win_rate = len(wins) / len(group) * 100
    avg_winner = wins['realized_profit'].mean() if len(wins) > 0 else 0
    avg_loser = losses['realized_profit'].mean() if len(losses) > 0 else 0
    expectancy = (win_rate/100 * avg_winner) + ((100-win_rate)/100 * avg_loser)
    total_profit = group['realized_profit'].sum()

    print(f"\n{'─'*60}")
    print(f"{label}")
    print(f"{'─'*60}")
    print(f"  Trades:      {len(group)}")
    print(f"  Win rate:     {win_rate:.1f}%")
    print(f"  Avg winner:   +{avg_winner:.4f} USDT")
    print(f"  Avg loser:    {avg_loser:.4f} USDT")
    print(f"  Expectancy:   {expectancy:+.4f} USDT/trade")
    print(f"  Total PnL:    {total_profit:+.4f} USDT")

    # Exit reason breakdown
    print(f"\n  Exit reasons:")
    exit_breakdown = group.groupby('exit_reason').agg(
        count=('realized_profit', 'count'),
        total=('realized_profit', 'sum')
    ).reset_index()
    for _, row in exit_breakdown.iterrows():
        print(f"    {row['exit_reason'] or 'NULL':<25}: {row['count']:>4} trades, {row['total']:+.4f} USDT")

    return {
        'trades': len(group),
        'win_rate': win_rate,
        'avg_winner': avg_winner,
        'avg_loser': avg_loser,
        'expectancy': expectancy,
        'total_profit': total_profit
    }

print("\n" + "="*70)
analyze_group(regime_up, "15m UPTREND at entry (allow trade)")
analyze_group(regime_down, "15m DOWNTREND at entry (skip trade)")

# What if we only traded during 15m uptrend?
print("\n" + "="*70)
print("DECISION ANALYSIS")
print("="*70)

all_profit = known['realized_profit'].sum()
filtered_profit = regime_up['realized_profit'].sum()
skipped_profit = regime_down['realized_profit'].sum()

print(f"\nCurrent (all trades):     {all_profit:+.4f} USDT on {len(known)} trades")
print(f"Filtered (15m up only):   {filtered_profit:+.4f} USDT on {len(regime_up)} trades")
print(f"Skipped trades PnL:      {skipped_profit:+.4f} USDT on {len(regime_down)} trades")

# Would we have improved?
if len(regime_up) > 0:
    filtered_expectancy = regime_up['realized_profit'].mean()
    current_expectancy = known['realized_profit'].mean()
    print(f"\nCurrent expectancy:      {current_expectancy:+.4f} USDT/trade")
    print(f"Filtered expectancy:     {filtered_expectancy:+.4f} USDT/trade")
    print(f"Improvement:             {(filtered_expectancy - current_expectancy):+.4f}")

    # Win rate comparison
    all_wr = (known['realized_profit'] > 0).mean() * 100
    filtered_wr = (regime_up['realized_profit'] > 0).mean() * 100
    print(f"\nCurrent win rate:        {all_wr:.1f}%")
    print(f"Filtered win rate:       {filtered_wr:.1f}%")
    print(f"Win rate improvement:   {filtered_wr - all_wr:+.1f}%")

    # Trade count reduction
    reduction = (1 - len(regime_up) / len(known)) * 100
    print(f"\nTrades filtered out:     {len(regime_down)} ({reduction:.1f}%)")
    print(f"Trades kept:            {len(regime_up)}")

print("\n" + "="*70)
print("VERDICT")
print("="*70)

if len(regime_up) > 0 and regime_up['realized_profit'].mean() > known['realized_profit'].mean():
    improvement = (regime_up['realized_profit'].mean() - known['realized_profit'].mean()) / abs(known['realized_profit'].mean()) * 100
    print(f"\n✓ 15m filter IMPROVES performance by {improvement:.1f}%")
    print(f"  Recommendation: Apply 15m SMA filter to entries")
else:
    improvement = (known['realized_profit'].mean() - regime_up['realized_profit'].mean()) / abs(known['realized_profit'].mean()) * 100
    print(f"\n✗ 15m filter does NOT improve performance")
    print(f"  The 5m signal is weak regardless of 15m regime")
    print(f"  Problem is deeper than timeframe alignment")