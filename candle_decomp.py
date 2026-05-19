#!/usr/bin/env python3
"""
Candle-by-Candle PnL Decomposition
Tracks price movement after each entry to find the signal decay pattern
"""
import sqlite3
import pandas as pd
import glob

def get_candle_after_entry(pair, open_date, candle_idx=0, data_dir='/freqtrade/user_data/data/binance'):
    """Get the Nth candle after entry"""
    pair_file = pair.replace('/', '_')
    pattern = f'{data_dir}/{pair_file}-5m.feather'
    files = glob.glob(pattern)
    if not files:
        return None

    try:
        df = pd.read_feather(files[0])
        open_dt = pd.to_datetime(open_date).tz_localize('UTC')
        # Find entry candle index
        df_valid = df[df['date'] >= open_dt]
        if len(df_valid) <= candle_idx:
            return None
        candle = df_valid.iloc[candle_idx]
        return candle
    except:
        return None

def compute_candle_pnl(trades_df, candle_idx, label):
    """Compute PnL at a specific candle after entry"""
    pnls = []
    for idx, trade in trades_df.iterrows():
        candle = get_candle_after_entry(trade['pair'], trade['open_date'], candle_idx)
        if candle is not None:
            entry_rate = trade['open_rate']
            # PnL as percentage of entry
            pnl_pct = (candle['close'] - entry_rate) / entry_rate
            pnls.append(pnl_pct)
    return pnls

print("=== CANDLE-BY-CANDLE PnL DECOMPOSITION ===")
print("Tracking price movement after entry signal fires\n")

conn = sqlite3.connect('/freqtrade/user_data/tradesv3_lea.sqlite')
trades = pd.read_sql(
    "SELECT id, pair, open_date, close_date, open_rate, close_rate, realized_profit, exit_reason "
    "FROM trades WHERE is_open=0 ORDER BY open_date DESC",
    conn
)
conn.close()

print(f"Analyzing {len(trades)} closed trades...")

# Compute PnL at each candle (0-10 candles after entry)
candles_data = {}
for i in range(11):
    pnls = compute_candle_pnl(trades, i, f"Candle {i}")
    if pnls:
        candles_data[i] = pnls

print("\n" + "="*70)
print(f"{'Candle':<10} | {'Count':>6} | {'Avg PnL%':>10} | {'Std Dev':>8} | {'Min':>8} | {'Max':>8}")
print("-"*70)

for idx in range(11):
    if idx in candles_data:
        pnls = candles_data[idx]
        avg = sum(pnls) / len(pnls) * 100
        std = (sum((p*100 - avg)**2 for p in pnls) / len(pnls)) ** 0.5
        min_p = min(pnls) * 100
        max_p = max(pnls) * 100
        print(f"Candle {idx:<4} | {len(pnls):>6} | {avg:>+10.3f}% | {std:>8.3f} | {min_p:>8.3f} | {max_p:>8.3f}%")
    else:
        print(f"Candle {idx:<4} | {'N/A':>6}")

# Entry price analysis
print("\n" + "="*70)
print("=== WHERE DO WINNERS GO AFTER ENTRY ===")
print("="*70)

# Check how many trades went positive at any point
positive_count = []
for idx, trade in trades.iterrows():
    pair_file = trade['pair'].replace('/', '_')
    pattern = f'/freqtrade/user_data/data/binance/{pair_file}-5m.feather'
    files = glob.glob(pattern)
    if not files:
        continue
    try:
        df = pd.read_feather(files[0])
        open_dt = pd.to_datetime(trade['open_date']).tz_localize('UTC')
        df_valid = df[df['date'] >= open_dt].head(30)  # 30 candles = 2.5h

        entry_rate = trade['open_rate']
        max_pnl = 0
        max_pnl_candle = 0

        for c_idx, candle in df_valid.iterrows():
            pnl = (candle['close'] - entry_rate) / entry_rate
            if pnl > max_pnl:
                max_pnl = pnl
                max_pnl_candle = len(df_valid[df_valid['date'] <= candle['date']])

        positive_count.append({
            'pair': trade['pair'],
            'realized_profit': trade['realized_profit'],
            'exit_reason': trade['exit_reason'],
            'max_pnl_pct': max_pnl * 100,
            'max_pnl_candle': max_pnl_candle
        })
    except:
        pass

positive_df = pd.DataFrame(positive_count)

# Distribution of max PnL reached
print("\nMax PnL reached during trade (before exit):")
buckets = [
    (0, 0.5, "0-0.5%"),
    (0.5, 1.0, "0.5-1%"),
    (1.0, 1.5, "1-1.5%"),
    (1.5, 2.0, "1.5-2%"),
    (2.0, 3.0, "2-3%"),
    (3.0, 5.0, "3-5%"),
    (5.0, 999, ">5%")
]
for low, high, label in buckets:
    cnt = len(positive_df[(positive_df['max_pnl_pct'] >= low) & (positive_df['max_pnl_pct'] < high)])
    pct = cnt / len(positive_df) * 100 if len(positive_df) > 0 else 0
    bar = '█' * int(pct / 2)
    print(f"  {label:>10}: {cnt:>4} ({pct:5.1f}%) {bar}")

# Trades that went positive but still lost
went_positive = positive_df[positive_df['max_pnl_pct'] > 0]
still_lost = went_positive[went_positive['realized_profit'] < 0]
print(f"\nTrades that reached +X% but still lost: {len(still_lost)} / {len(went_positive)}")
print(f"  Avg max_pnl of these: {still_lost['max_pnl_pct'].mean():.2f}%")

# Top winners - what candle did they peak at?
print("\n" + "="*70)
print("=== CANDLE WHERE MAX PNL REACHED ===")
print("="*70)
candle_buckets = [
    (0, 1, "Candle 0-1"),
    (1, 3, "Candle 1-3"),
    (3, 6, "Candle 3-6"),
    (6, 12, "Candle 6-12"),
    (12, 30, "Candle 12-30"),
    (30, 999, ">Candle 30")
]
for low, high, label in candle_buckets:
    cnt = len(positive_df[(positive_df['max_pnl_candle'] >= low) & (positive_df['max_pnl_candle'] < high)])
    pct = cnt / len(positive_df) * 100 if len(positive_df) > 0 else 0
    print(f"  {label:>12}: {cnt:>4} ({pct:5.1f}%)")

# Avg candle of max Pnl
avg_candle = positive_df['max_pnl_candle'].mean()
print(f"\n  Average candle where max PnL reached: {avg_candle:.1f} (~{avg_candle*5:.0f} minutes)")

# Signal validity window analysis
print("\n" + "="*70)
print("=== TRAILING STOP TIMING ANALYSIS ===")
print("="*70)
# If trailing stop kicks in on candle 1-3, that means signal dies fast
trailing_trades = positive_df[positive_df['exit_reason'] == 'trailing_stop_loss']
if len(trailing_trades) > 0:
    print(f"\nTrailing stop exits: {len(trailing_trades)}")
    print(f"  Avg max PnL reached: {trailing_trades['max_pnl_pct'].mean():.2f}%")
    print(f"  Avg candle of max PnL: {trailing_trades['max_pnl_candle'].mean():.1f}")
    print(f"  Max PnL distribution:")
    for low, high, label in [(0, 1, "0-1%"), (1, 2, "1-2%"), (2, 3, "2-3%"), (3, 999, ">3%")]:
        cnt = len(trailing_trades[(trailing_trades['max_pnl_pct'] >= low) & (trailing_trades['max_pnl_pct'] < high)])
        pct = cnt / len(trailing_trades) * 100
        print(f"    {label:>6}: {cnt:>4} ({pct:5.1f}%)")