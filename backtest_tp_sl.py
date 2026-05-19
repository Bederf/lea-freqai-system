#!/usr/bin/env python3
"""
Backtest: Remove trailing stop + Add +1.5% fixed take-profit
Compare to actual results to see if exit change fixes the strategy
"""
import sqlite3
import pandas as pd
import glob

print("="*70)
print("EXIT STRATEGY BACKTEST: +1.5% TP vs -5% SL (No Trailing Stop)")
print("="*70)

conn = sqlite3.connect('/freqtrade/user_data/tradesv3_lea.sqlite')
trades = pd.read_sql(
    "SELECT id, pair, open_date, close_date, open_rate, realized_profit, exit_reason "
    "FROM trades WHERE is_open=0 ORDER BY open_date DESC LIMIT 50",
    conn
)
conn.close()

print(f"Analyzing {len(trades)} trades...")

# Cache 5m data
data_dir = '/freqtrade/user_data/data/binance'
cache = {}
for pair in trades['pair'].unique():
    pair_file = pair.replace('/', '_')
    pattern = f'{data_dir}/{pair_file}-5m.feather'
    files = glob.glob(pattern)
    if files:
        try:
            cache[pair] = pd.read_feather(files[0])
        except:
            pass

print(f"Cached {len(cache)} pairs")

TP_PCT = 0.015  # 1.5% take-profit
SL_PCT = 0.05   # 5% stop-loss

def simulate_exit(pair, open_date, open_rate):
    """Simulate TP/SL exit on real candle data"""
    if pair not in cache:
        return None, None, None

    df = cache[pair]
    open_dt = pd.to_datetime(open_date).tz_localize('UTC')
    df_valid = df[df['date'] >= open_dt].head(120)  # Max 120 candles (10h)

    if len(df_valid) < 2:
        return None, None, None

    entry = open_rate
    tp_price = entry * (1 + TP_PCT)
    sl_price = entry * (1 - SL_PCT)

    for i, (_, candle) in enumerate(df_valid.iterrows()):
        high = candle['high']
        low = candle['low']
        close = candle['close']

        # Check TP hit (price reached TP level at any point)
        if high >= tp_price:
            return 'tp_hit', i+1, TP_PCT  # exited on candle i

        # Check SL hit
        if low <= sl_price:
            return 'sl_hit', i+1, -SL_PCT  # exited on candle i

    # Neither hit - check what close was at end
    final_close = df_valid.iloc[-1]['close']
    final_pnl = (final_close - entry) / entry

    # Cap at some reasonable time (60 candles = 5h)
    return 'timeout', len(df_valid), final_pnl

# Simulate
results = []
for idx, trade in trades.iterrows():
    result, candles, pnl = simulate_exit(trade['pair'], trade['open_date'], trade['open_rate'])
    if result:
        results.append({
            'pair': trade['pair'],
            'exit_simulated': result,
            'candles_held': candles,
            'simulated_pnl': pnl,
            'actual_pnl': trade['realized_profit'],
            'actual_exit': trade['exit_reason']
        })

rdf = pd.DataFrame(results)

# Analyze
print(f"\n{'='*70}")
print("SIMULATED RESULTS (TP=1.5%, SL=5%, No Trailing)")
print(f"{'='*70}")

tp_trades = rdf[rdf['exit_simulated'] == 'tp_hit']
sl_trades = rdf[rdf['exit_simulated'] == 'sl_hit']
timeout_trades = rdf[rdf['exit_simulated'] == 'timeout']

print(f"\nTake-profit hits: {len(tp_trades)} ({len(tp_trades)/len(rdf)*100:.1f}%)")
print(f"Stop-loss hits: {len(sl_trades)} ({len(sl_trades)/len(rdf)*100:.1f}%)")
print(f"Timeout (no trigger): {len(timeout_trades)} ({len(timeout_trades)/len(rdf)*100:.1f}%)")

def group_stats(label, df):
    if len(df) == 0:
        return
    wr = (df['simulated_pnl'] > 0).mean() * 100
    wins = df[df['simulated_pnl'] > 0]['simulated_pnl']
    losses = df[df['simulated_pnl'] < 0]['simulated_pnl']
    avg_w = wins.mean() if len(wins) > 0 else 0
    avg_l = losses.mean() if len(losses) > 0 else 0
    total = df['simulated_pnl'].sum()
    exp = (wr/100 * avg_w) + ((100-wr)/100 * avg_l)
    print(f"\n{label}")
    print(f"  Count: {len(df)}")
    print(f"  Win rate: {wr:.1f}%")
    print(f"  Avg winner: +{avg_w:.4f} ({avg_w*100:.2f}%)")
    print(f"  Avg loser: {avg_l:.4f} ({avg_l*100:.2f}%)")
    print(f"  Expectancy: {exp:+.4f} ({exp*100:+.2f}%)")
    print(f"  Total PnL: {total:+.4f} ({total*100:.2f}%)")

group_stats("TAKE-PROFIT EXITS:", tp_trades)
group_stats("STOP-LOSS EXITS:", sl_trades)
group_stats("TIMEOUT EXITS:", timeout_trades)

# Combined
all_wins = rdf[rdf['simulated_pnl'] > 0]
all_losses = rdf[rdf['simulated_pnl'] < 0]
wr = len(all_wins) / len(rdf) * 100
avg_w = all_wins['simulated_pnl'].mean() if len(all_wins) > 0 else 0
avg_l = all_losses['simulated_pnl'].mean() if len(all_losses) > 0 else 0
exp = (wr/100 * avg_w) + ((100-wr)/100 * avg_l)
total = rdf['simulated_pnl'].sum()

print(f"\n{'='*70}")
print("COMBINED SIMULATED PERFORMANCE")
print(f"{'='*70}")
print(f"Total trades: {len(rdf)}")
print(f"Win rate: {wr:.1f}%")
print(f"Avg winner: +{avg_w:.4f} ({avg_w*100:.2f}%)")
print(f"Avg loser: {avg_l:.4f} ({avg_l*100:.2f}%)")
print(f"Expectancy: {exp:+.4f} ({exp*100:+.2f}%)")
print(f"Total PnL: {total:+.4f} ({total*100:.2f}%)")

# Compare to actual
actual_wr = (rdf['actual_pnl'] > 0).mean() * 100
actual_wins = rdf[rdf['actual_pnl'] > 0]['actual_pnl']
actual_losses = rdf[rdf['actual_pnl'] < 0]['actual_pnl']
actual_avg_w = actual_wins.mean() if len(actual_wins) > 0 else 0
actual_avg_l = actual_losses.mean() if len(actual_losses) > 0 else 0
actual_total = rdf['actual_pnl'].sum()

print(f"\n{'='*70}")
print("COMPARISON: SIMULATED vs ACTUAL")
print(f"{'='*70}")
print(f"                    SIMULATED      ACTUAL        CHANGE")
print(f"Win rate:          {wr:>10.1f}%    {actual_wr:>10.1f}%    {wr-actual_wr:>+7.1f}%")
print(f"Avg winner:        {avg_w*100:>+10.2f}%    {actual_avg_w*100:>+10.4f}%    {(avg_w-actual_avg_w)*100:>+7.2f}%")
print(f"Avg loser:         {avg_l*100:>+10.2f}%    {actual_avg_l*100:>+10.2f}%    {(avg_l-actual_avg_l)*100:>+7.2f}%")
print(f"Total PnL:         {total*100:>+10.2f}%    {actual_total*100:>+10.2f}%    {(total-actual_total)*100:>+7.2f}%")

print(f"\n{'='*70}")
print("VERDICT")
print(f"{'='*70}")
if exp > actual_total / len(rdf):
    print(f"\n✓ NEW exit strategy IMPROVES expectancy by {(exp - actual_total/len(rdf))*100:.2f}%")
    print(f"  Recommendation: Remove trailing stop, add +1.5% TP")
else:
    print(f"\n✗ Exit change does NOT improve performance")
    print(f"  Signal still cannot produce enough winners to cover losses")