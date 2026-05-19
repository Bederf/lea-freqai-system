#!/usr/bin/env python3
"""
Regime-Stratified Performance Analyzer
Analyzes trade performance split by regime (uptrend vs downtrend at entry)
"""

import sqlite3
import pandas as pd
import numpy as np
from scipy import stats
import glob
import os

def compute_regime(df):
    """Compute 1h regime from 5m data: sma_12 > sma_48 = uptrend"""
    df = df.copy()
    df['sma_12'] = df['close'].rolling(12).mean()
    df['sma_48'] = df['close'].rolling(48).mean()
    df['regime'] = (df['sma_12'] > df['sma_48']).astype(int)
    return df

def load_trades(db_path):
    """Load closed trades from SQLite"""
    conn = sqlite3.connect(db_path)
    trades_df = pd.read_sql("""
        SELECT id, pair, open_date, close_date, open_rate, close_rate,
               stake_amount, realized_profit, close_profit_abs, is_open, exit_reason
        FROM trades
        WHERE is_open = 0
        ORDER BY open_date DESC
    """, conn)
    conn.close()
    return trades_df

def get_regime_at_entry(pair, open_date, data_dir='/freqtrade/user_data/data/binance'):
    """Get regime at entry time from 5m candle data"""
    pair_file = pair.replace('/', '_')
    pattern = f'{data_dir}/{pair_file}-5m.feather'

    files = glob.glob(pattern)
    if not files:
        return -1  # unknown

    try:
        df = pd.read_feather(files[0])
        df = compute_regime(df)

        open_dt = pd.to_datetime(open_date).tz_localize('UTC') if pd.to_datetime(open_date).tzinfo is None else pd.to_datetime(open_date)
        # Find last valid candle at or before open_date
        df_valid = df[df['date'] <= open_dt]
        if len(df_valid) > 0:
            return int(df_valid.iloc[-1]['regime'])
        return -1
    except Exception as e:
        return -1

def analyze_regime_group(group, group_name):
    """Analyze performance for a regime group"""
    if len(group) == 0:
        return None

    wins = group[group['realized_profit'] > 0]
    losses = group[group['realized_profit'] < 0]

    win_rate = len(wins) / len(group) * 100
    avg_winner = wins['realized_profit'].mean() if len(wins) > 0 else 0
    avg_loser = losses['realized_profit'].mean() if len(losses) > 0 else 0

    # Expectancy: P(win) * avg_win + P(loss) * avg_loss
    expectancy = (win_rate/100 * avg_winner) + ((100-win_rate)/100 * avg_loser)

    # Drawdown (worst consecutive loss streak)
    group_sorted = group.sort_values('close_date')
    pnl_series = group_sorted['realized_profit'].values
    max_drawdown = 0
    running_max = 0
    for pnl in pnl_series:
        running_max = max(running_max, pnl)
        drawdown = running_max - pnl
        max_drawdown = max(max_drawdown, drawdown)

    # Consecutive losses
    max_consec_loss = 0
    current_streak = 0
    for pnl in pnl_series:
        if pnl < 0:
            current_streak += 1
            max_consec_loss = max(max_consec_loss, current_streak)
        else:
            current_streak = 0

    total_profit = group['realized_profit'].sum()

    return {
        'group': group_name,
        'trades': len(group),
        'win_rate': win_rate,
        'avg_winner': avg_winner,
        'avg_loser': avg_loser,
        'expectancy': expectancy,
        'max_drawdown': max_drawdown,
        'max_consec_loss': max_consec_loss,
        'total_profit': total_profit
    }

def chi_square_test(regime_true, regime_false):
    """Chi-square test: is the win rate difference statistically significant?"""
    # Contingency table: [wins, losses] for each regime
    true_wins = (regime_true['realized_profit'] > 0).sum()
    true_losses = len(regime_true) - true_wins
    false_wins = (regime_false['realized_profit'] > 0).sum()
    false_losses = len(regime_false) - false_wins

    contingency = [[true_wins, true_losses],
                    [false_wins, false_losses]]

    if any(c == 0 for c in [true_wins, true_losses, false_wins, false_losses]):
        return None, None  # Can't compute with zeros

    chi2, p_value, dof, expected = stats.chi2_contingency(contingency)
    return chi2, p_value

def main():
    # Load trades from LEA database (has history)
    db_path = '/freqtrade/user_data/tradesv3_lea.sqlite'
    trades = load_trades(db_path)

    print(f"\n{'='*70}")
    print(f"REGIME-STRATIFIED PERFORMANCE ANALYSIS")
    print(f"{'='*70}")
    print(f"\nTotal closed trades: {len(trades)}")
    print(f"Date range: {trades['open_date'].min()} to {trades['open_date'].max()}")

    # Label each trade with regime at entry
    print("\nLabeling regime at entry for each trade...")
    regimes = []
    for idx, trade in trades.iterrows():
        regime = get_regime_at_entry(trade['pair'], trade['open_date'])
        regimes.append(regime)

    trades = trades.copy()
    trades['regime_at_entry'] = regimes

    known = trades[trades['regime_at_entry'] >= 0]
    unknown = len(trades) - len(known)
    print(f"Regime labeled: {len(known)} trades, {unknown} unknown (no OHLCV data)")

    if len(known) == 0:
        print("\nERROR: No OHLCV data available for regime labeling.")
        print("Need to download 5m candle data for pairs first.")
        return

    # Split by regime
    regime_true = known[known['regime_at_entry'] == 1]
    regime_false = known[known['regime_at_entry'] == 0]

    print(f"\nRegime=TRUE (uptrend at entry):  {len(regime_true)} trades")
    print(f"Regime=FALSE (downtrend at entry): {len(regime_false)} trades")

    # Analyze each group
    true_stats = analyze_regime_group(regime_true, 'regime=TRUE')
    false_stats = analyze_regime_group(regime_false, 'regime=FALSE')

    # Chi-square test for statistical significance
    chi2, p_value = chi_square_test(regime_true, regime_false)

    # Print results
    print(f"\n{'─'*70}")
    print(f"REGIME = TRUE (uptrend at entry)")
    print(f"{'─'*70}")
    if true_stats:
        print(f"  Trades:         {true_stats['trades']}")
        print(f"  Win rate:        {true_stats['win_rate']:.1f}%")
        print(f"  Avg winner:      +{true_stats['avg_winner']:.4f} USDT")
        print(f"  Avg loser:       {true_stats['avg_loser']:.4f} USDT")
        print(f"  Expectancy:      {true_stats['expectancy']:+.4f} USDT/trade")
        print(f"  Max drawdown:    {true_stats['max_drawdown']:.4f} USDT")
        print(f"  Max consec loss: {true_stats['max_consec_loss']}")
        print(f"  Total profit:    {true_stats['total_profit']:+.4f} USDT")

    print(f"\n{'─'*70}")
    print(f"REGIME = FALSE (downtrend at entry)")
    print(f"{'─'*70}")
    if false_stats:
        print(f"  Trades:         {false_stats['trades']}")
        print(f"  Win rate:        {false_stats['win_rate']:.1f}%")
        print(f"  Avg winner:      +{false_stats['avg_winner']:.4f} USDT")
        print(f"  Avg loser:       {false_stats['avg_loser']:.4f} USDT")
        print(f"  Expectancy:      {false_stats['expectancy']:+.4f} USDT/trade")
        print(f"  Max drawdown:    {false_stats['max_drawdown']:.4f} USDT")
        print(f"  Max consec loss: {false_stats['max_consec_loss']}")
        print(f"  Total profit:    {false_stats['total_profit']:+.4f} USDT")

    # Statistical significance
    print(f"\n{'─'*70}")
    print(f"STATISTICAL SIGNIFICANCE")
    print(f"{'─'*70}")
    if p_value is not None:
        significance = "YES" if p_value < 0.05 else "NO"
        print(f"  Chi-square:      {chi2:.3f}")
        print(f"  P-value:         {p_value:.4f}")
        print(f"  Significant (p<0.05): {significance}")
        if p_value < 0.05:
            print(f"\n  → The regime filter is REAL, not luck.")
            print(f"  → Trading only in regime=TRUE would significantly improve results.")
        else:
            print(f"\n  → The regime difference is NOT statistically significant.")
            print(f"  → Regime filter alone doesn't guarantee better results.")
    else:
        print("  Cannot compute (insufficient data)")

    # Decision recommendation
    print(f"\n{'═'*70}")
    print(f"DECISION")
    print(f"{'═'*70}")
    if true_stats and false_stats:
        # Estimate filtered performance
        filtered_est = true_stats['expectancy'] * len(regime_true)
        all_est = true_stats['expectancy'] * len(regime_true) + false_stats['expectancy'] * len(regime_false)
        current_total = trades['realized_profit'].sum()

        print(f"\n  Current (all trades): {current_total:+.4f} USDT on {len(trades)} trades")
        print(f"  Filtered (regime=TRUE only): est. {filtered_est:+.4f} USDT on {len(regime_true)} trades")

        if true_stats['win_rate'] > false_stats['win_rate'] and true_stats['expectancy'] > 0:
            print(f"\n  RECOMMENDATION: Filter regime=FALSE trades.")
            print(f"  Estimated improvement: {filtered_est - all_est:+.4f} USDT")
        elif true_stats['expectancy'] > false_stats['expectancy']:
            print(f"\n  RECOMMENDATION: Regime filter improves expectancy.")
        else:
            print(f"\n  RECOMMENDATION: Regime alone is not strong enough filter.")
            print(f"  Consider combining with volume or RSI filters.")

if __name__ == '__main__':
    main()