#!/usr/bin/env python3
"""
Replay Exit Analysis — LeahAI
==============================
For every trade that exited via time_exit_6h_negative, replay the price
path after the forced exit to see if holding longer would have recovered.

Outputs:
  - Per-trade replay table: what would have happened at +2h, +4h, +8h after exit
  - Aggregate: what % of time-exit losers would have turned into winners if held
  - MFE/MAE by holding period

Usage:
  python3 replay_exits.py [--db <path>] [--output-dir <dir>]
"""

import sqlite3
import os
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

# ─── Load closed time_exit trades ─────────────────────────────────────────────

def get_time_exit_trades(db_path: str) -> pd.DataFrame | None:
    if not os.path.exists(db_path):
        return None

    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("""
        SELECT
            t.id,
            t.pair,
            t.open_rate,
            t.close_rate,
            t.realized_profit,
            t.fee_open_cost,
            t.fee_close_cost,
            t.open_date,
            t.close_date,
            t.stake_amount,
            t.enter_tag,
            t.strategy,
            t.timeframe
        FROM trades t
        WHERE t.exit_reason = 'time_exit_6h_negative'
          AND t.is_open = 0
        ORDER BY t.open_date
    """, conn, parse_dates=["open_date", "close_date"])
    conn.close()
    return df


def load_candle_data(pair: str, start: datetime, end: datetime, timeframe: str = "5m") -> pd.DataFrame | None:
    """
    Load candle data from feather files in user_data/data/{exchange}/{pair}-{timeframe}.feather.
    Columns: date, open, high, low, close, volume
    """
    from pathlib import Path

    base = Path("user_data/data/binance")
    if not base.exists():
        return None

    pair_clean = pair.replace('/', '_')
    # Normalize timeframe: 5 → "5m", "5" → "5m", "5m" → "5m"
    if str(timeframe).isdigit():
        timeframe_str = f"{timeframe}m"
    elif not str(timeframe).endswith('m'):
        timeframe_str = f"{timeframe}m"
    else:
        timeframe_str = str(timeframe)
    candle_file = base / f"{pair_clean}-{timeframe_str}.feather"

    if not candle_file.exists():
        return None

    try:
        df = pd.read_feather(candle_file)
        df = df.rename(columns={"date": "timestamp"})
        # Candle timestamps are UTC-aware; ensure comparison is too
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
        else:
            df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")

        # Ensure start/end are UTC-aware for comparison
        if start.tzinfo is None:
            start = start.tz_localize("UTC")
        if end.tzinfo is None:
            end = end.tz_localize("UTC")

        # Filter to window of interest
        df = df[
            (df["timestamp"] >= start - timedelta(hours=24)) &
            (df["timestamp"] <= end + timedelta(hours=24))
        ]
        return df.sort_values("timestamp").reset_index(drop=True)
    except Exception as e:
        print(f"    [WARN] Could not load {candle_file}: {e}")
        return None


def replay_trade(trade: pd.Series, candles: pd.DataFrame, lookahead_hours: int = 12) -> dict | None:
    """
    For a given trade, replay what would have happened if we held for `lookahead_hours`
    after the original forced exit.

    Returns a dict with:
      - original_exit_price, original_exit_time
      - price at +2h, +4h, +6h, +8h, +12h after exit
      - max price in lookahead window (MFE)
      - min price in lookahead window (MAE)
      - Would it have recovered to entry / to a winner?
    """
    if candles is None or candles.empty:
        return None

    entry_time = trade["open_date"]
    entry_price = trade["open_rate"]
    exit_time = trade["close_date"]
    exit_price = trade["close_rate"]

    # Ensure tz-aware for comparison with candle timestamps
    if exit_time.tzinfo is None:
        exit_time = exit_time.tz_localize("UTC")
    if entry_time.tzinfo is None:
        entry_time = entry_time.tz_localize("UTC")

    # Candles after exit
    after_exit = candles[candles["timestamp"] > exit_time].head(lookahead_hours * 12)  # 5m candles

    if after_exit.empty:
        return None

    # Helper: price at N hours after exit
    def price_at(hours: float) -> float | None:
        target = exit_time + timedelta(hours=hours)
        # Find nearest candle
        idx = after_exit["timestamp"].searchsorted(target)
        if idx >= len(after_exit):
            return None
        return float(after_exit.iloc[idx]["close"])

    # MFE / MAE in the lookahead window
    high_in_window = after_exit["high"].max()
    low_in_window = after_exit["low"].min()
    mfe_pct = (high_in_window - entry_price) / entry_price * 100
    mae_pct = (entry_price - low_in_window) / entry_price * 100

    # Max close in window
    max_close = after_exit["close"].max()
    min_close = after_exit["close"].min()

    # Would it have recovered to entry by various horizons?
    def recovered_by(hours: float) -> bool | None:
        p = price_at(hours)
        if p is None:
            return None
        return p >= entry_price

    # Would it have been a winner (exceeded ROI target) at various horizons?
    # Using 2% as the minimum "winner" threshold
    def winner_by(hours: float, threshold: float = 0.02) -> bool | None:
        p = price_at(hours)
        if p is None:
            return None
        return (p - entry_price) / entry_price >= threshold

    result = {
        "trade_id": trade["id"],
        "pair": trade["pair"],
        "open_date": entry_time,
        "close_date": exit_time,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "stake_amount": trade["stake_amount"],
        "realized_profit": trade["realized_profit"],
        "holding_minutes": (exit_time - entry_time).total_seconds() / 60,
        # Lookahead
        f"price_+2h": price_at(2),
        f"price_+4h": price_at(4),
        f"price_+6h": price_at(6),
        f"price_+8h": price_at(8),
        f"price_+12h": price_at(12),
        # MFE/MAE in lookahead window
        "lookahead_mfe_pct": round(mfe_pct, 3),
        "lookahead_mae_pct": round(mae_pct, 3),
        "lookahead_max_close": max_close,
        "lookahead_min_close": min_close,
        # Recovery
        f"recovered_+2h": recovered_by(2),
        f"recovered_+4h": recovered_by(4),
        f"recovered_+6h": recovered_by(6),
        f"recovered_+8h": recovered_by(8),
        # Winner at +2h (2% threshold)
        f"winner_+2h": winner_by(2),
        f"winner_+4h": winner_by(4),
        f"winner_+6h": winner_by(6),
        f"winner_+8h": winner_by(8),
    }
    return result


def run_replay(dbs: list[str], lookahead: int = 12) -> pd.DataFrame:
    all_results = []

    for db_path in dbs:
        trades = get_time_exit_trades(db_path)
        if trades is None or trades.empty:
            print(f"  No time-exit trades in {db_path}")
            continue

        print(f"  Replaying {len(trades)} time-exit trades from {db_path}...")

        for _, trade in trades.iterrows():
            candles = load_candle_data(
                trade["pair"],
                trade["open_date"],
                trade["close_date"] + timedelta(hours=lookahead + 2),
                str(trade.get("timeframe", "5m") or "5m"),
            )
            result = replay_trade(trade, candles, lookahead)
            if result:
                result["source_db"] = os.path.basename(db_path)
                all_results.append(result)

    return pd.DataFrame(all_results)


def analyze_replay(replay_df: pd.DataFrame, lookahead: int = 12) -> dict:
    """
    Aggregate analysis of the replay:
      - % of trades that would have recovered to entry at each horizon
      - % that would have been winners (>2% profit) at each horizon
      - MFE vs realized profit
    """
    recovery_cols = [c for c in replay_df.columns if c.startswith("recovered_")]
    winner_cols = [c for c in replay_df.columns if c.startswith("winner_")]
    price_cols = [c for c in replay_df.columns if c.startswith("price_")]

    horizons = ["+2h", "+4h", "+6h", "+8h", "+12h"]

    recovery_rates = {}
    winner_rates = {}

    for h in horizons:
        rc = f"recovered_{h}"
        wc = f"winner_{h}"
        pc = f"price_{h}"

        if rc in replay_df.columns:
            valid = replay_df[rc].dropna()
            if len(valid) > 0:
                recovery_rates[h] = f"{valid.sum()}/{len(valid)} ({valid.mean()*100:.1f}%)"

        if wc in replay_df.columns:
            valid = replay_df[wc].dropna()
            if len(valid) > 0:
                winner_rates[h] = f"{valid.sum()}/{len(valid)} ({valid.mean()*100:.1f}%)"

    return {
        "recovery_rates": recovery_rates,
        "winner_rates": winner_rates,
        "avg_mfe_in_lookahead": round(replay_df["lookahead_mfe_pct"].mean(), 3),
        "avg_mae_in_lookahead": round(replay_df["lookahead_mae_pct"].mean(), 3),
        "mfe_gt_2pct": (replay_df["lookahead_mfe_pct"] > 2.0).sum(),
        "mae_lt_2pct": (replay_df["lookahead_mae_pct"] < 2.0).sum(),
        "trades_replayed": len(replay_df),
    }


def print_replay_report(replay_df: pd.DataFrame, analysis: dict, lookahead: int):
    print(f"\n{'='*60}")
    print("TIME-EXIT REPLAY ANALYSIS")
    print(f"{'='*60}")

    print(f"\n  Trades replayed: {analysis['trades_replayed']}")
    print(f"  Avg MFE in lookahead window: {analysis['avg_mfe_in_lookahead']}%")
    print(f"  Avg MAE in lookahead window: {analysis['avg_mae_in_lookahead']}%")

    print(f"\n{'RECOVERY TO ENTRY BY HORIZON':=^50}")
    for h, rate in analysis["recovery_rates"].items():
        print(f"  {h}: {rate}")

    print(f"\n{'BECOME WINNER (>2% PROFIT) BY HORIZON':=^50}")
    for h, rate in analysis["winner_rates"].items():
        print(f"  {h}: {rate}")

    print(f"\n{'TRADE-LEVEL REPLAY TABLE':=^50}")
    cols = ["trade_id", "pair", "entry_price", "exit_price", "holding_minutes",
            "lookahead_mfe_pct", "lookahead_mae_pct", "recovered_+2h", "recovered_+6h", "winner_+2h", "winner_+6h"]
    available = [c for c in cols if c in replay_df.columns]
    print(replay_df[available].to_string(index=False))

    print(f"\n{'INTERPRETATION':=^50}")
    mfe_2x = analysis["avg_mfe_in_lookahead"]
    mae_2x = analysis["avg_mae_in_lookahead"]
    if mfe_2x > 3.0 and mae_2x < 2.0:
        print("  → MFE is much larger than MAE. Trades had significant upside")
        print("    after the forced exit but price reversed. Exit was too aggressive.")
    elif mfe_2x < 2.0 and mae_2x > 3.0:
        print("  → MAE exceeds MFE. Price continued falling after exit.")
        print("    The time exit was protective — removing it would increase losses.")
    else:
        print(f"  → MFE={mfe_2x}%, MAE={mae_2x}% — mixed signals.")


# ─── Fix breakeven in the main report ─────────────────────────────────────────

def compute_ev_metrics(df: pd.DataFrame) -> dict:
    """Compute EV metrics with correct breakeven formula."""
    closed = df[df["is_open"] == 0].copy()
    wins = closed[closed["net_profit"] > 0]
    losses = closed[closed["net_profit"] <= 0]

    avg_win = wins["net_profit"].mean() if len(wins) > 0 else 0
    avg_loss = losses["net_profit"].mean() if len(losses) > 0 else 0

    win_rate = len(wins) / len(closed) if len(closed) > 0 else 0

    # Correct breakeven WR formula: avg_loss / (avg_loss + avg_win)
    # Derived from: win_rate * avg_win = loss_rate * |avg_loss|
    #              win_rate * avg_win = (1 - win_rate) * |avg_loss|
    #              win_rate * avg_win = |avg_loss| - win_rate * |avg_loss|
    #              win_rate * (avg_win + |avg_loss|) = |avg_loss|
    #              win_rate = |avg_loss| / (avg_win + |avg_loss|)
    be_wr = abs(avg_loss) / (abs(avg_loss) + avg_win) if avg_win > 0 else 1.0

    return {
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "be_wr": be_wr,
        "wr_vs_be_gap": win_rate - be_wr,  # negative = below breakeven
    }


# ─── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", action="append", dest="dbs", default=[])
    parser.add_argument("--output-dir", default="user_data/reports")
    parser.add_argument("--lookahead", type=int, default=12)
    args = parser.parse_args()

    if not args.dbs:
        args.dbs = [
            "user_data/tradesv3_lea_v2.sqlite",
            "user_data/tradesv3_lea_v5.sqlite",
            "user_data/tradesv3_lea_v6.sqlite",
        ]

    os.makedirs(args.output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ─ Replay time-exit trades ─────────────────────────────────────────────────
    print(f"Loading replay data from: {args.dbs}")
    replay_df = run_replay(args.dbs, lookahead=args.lookahead)

    if replay_df.empty:
        print("No time-exit trades found for replay. Check exit_reason values in DB.")
        replay_df.to_csv(f"{args.output_dir}/replay_raw_{date_str}.csv", index=False)
    else:
        analysis = analyze_replay(replay_df, lookahead=args.lookahead)
        print_replay_report(replay_df, analysis, args.lookahead)

        replay_df.to_csv(f"{args.output_dir}/replay_trades_{date_str}.csv", index=False)
        print(f"\n  Saved: {args.output_dir}/replay_trades_{date_str}.csv")

    # ─ Verify EV metrics ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("EV METRICS VERIFICATION")
    print(f"{'='*60}")

    for db_path in args.dbs:
        if not os.path.exists(db_path):
            continue
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("""
            SELECT *,
                   realized_profit - fee_open_cost - fee_close_cost as net_profit
            FROM trades WHERE is_open = 0
        """, conn, parse_dates=["open_date", "close_date"])
        conn.close()

        ev = compute_ev_metrics(df)
        db_name = os.path.basename(db_path)
        print(f"\n  {db_name}:")
        print(f"    Trades: {len(df)}")
        print(f"    Win rate: {ev['win_rate']*100:.1f}%")
        print(f"    Avg win: ${ev['avg_win']:.4f}")
        print(f"    Avg loss: ${ev['avg_loss']:.4f}")
        print(f"    Breakeven WR: {ev['be_wr']*100:.1f}%")
        print(f"    WR vs BE gap: {ev['wr_vs_be_gap']*100:+.1f}pp  {'✅' if ev['wr_vs_be_gap'] >= 0 else '❌ BELOW BREAKEVEN'}")
