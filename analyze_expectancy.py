#!/usr/bin/env python3
"""
LeahAI Strategy Expectancy Report
=================================
Produces a comprehensive strategy expectancy report from Freqtrade trade databases.
Saves: results/lea_expectancy_report_v{version}_{date}.csv
       results/lea_expectancy_report_v{version}_{date}.md

Usage: python3 analyze_expectancy.py [--db <path>] [--output-dir <dir>]
"""

import sqlite3
import os
import sys
import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ─── Argument parsing ──────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="LeahAI expectancy report generator")
parser.add_argument("--db", action="append", dest="dbs", default=[], help="Database path(s)")
parser.add_argument("--output-dir", default="user_data/reports", help="Output directory")
parser.add_argument("--label", default="", help="Label for this report (e.g. 'v6_baseline')")
args = parser.parse_args()

if not args.dbs:
    args.dbs = [
        "user_data/tradesv3_lea_v2.sqlite",
        "user_data/tradesv3_lea_v5.sqlite",
        "user_data/tradesv3_lea_v6.sqlite",
    ]

# ─── Load trade data ───────────────────────────────────────────────────────────

def load_trades(db_path: str) -> pd.DataFrame | None:
    if not os.path.exists(db_path):
        print(f"  [SKIP] {db_path} — not found")
        return None

    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("""
        SELECT
            id,
            pair,
            is_open,
            open_rate,
            close_rate,
            realized_profit,
            fee_open_cost,
            fee_close_cost,
            stake_amount,
            enter_tag,
            exit_reason,
            open_date,
            close_date,
            max_rate,
            min_rate,
            stop_loss_pct,
            initial_stop_loss_pct,
            strategy,
            trading_mode,
            leverage,
            funding_fees
        FROM trades
        ORDER BY open_date
    """, conn, parse_dates=["open_date", "close_date"])
    conn.close()

    if df.empty:
        return None

    # Net profit including fees
    df["net_profit"] = df["realized_profit"] - df["fee_open_cost"].fillna(0) - df["fee_close_cost"].fillna(0)
    df["is_win"] = df["net_profit"] > 0

    # Holding time in minutes
    df["holding_minutes"] = (
        (df["close_date"] - df["open_date"]).dt.total_seconds() / 60
    )

    # MFE / MAE using max_rate / min_rate vs open_rate
    df["mfe_pct"] = (df["max_rate"] - df["open_rate"]) / df["open_rate"] * 100
    df["mae_pct"] = (df["open_rate"] - df["min_rate"]) / df["open_rate"] * 100

    # Parse enter_tag for confidence
    def parse_prob(tag: str) -> float | None:
        if not tag:
            return None
        # Handles: prob_0.8503  or  garch_0.863_lvl_0.021_pe_0.88_dur_3
        for prefix in ["prob_", "garch_"]:
            if tag.startswith(prefix):
                try:
                    return float(tag.split("_")[1])
                except (IndexError, ValueError):
                    pass
        return None

    df["confidence"] = df["enter_tag"].apply(parse_prob)

    # Confidence buckets
    def bucket(conf: float | None) -> str:
        if conf is None:
            return "untagged"
        if conf < 0.55:
            return "< 0.55"
        elif conf < 0.60:
            return "0.55–0.60"
        elif conf < 0.70:
            return "0.60–0.70"
        elif conf < 0.80:
            return "0.70–0.80"
        elif conf < 0.90:
            return "0.80–0.90"
        else:
            return "0.90+"

    df["conf_bucket"] = df["confidence"].apply(bucket)

    db_name = os.path.basename(db_path)
    df["source_db"] = db_name
    return df

# ─── Overall stats ─────────────────────────────────────────────────────────────

def overall_stats(df: pd.DataFrame) -> dict:
    closed = df[df["is_open"] == 0].copy()
    open_trades = df[df["is_open"] == 1]

    wins = closed[closed["is_win"]]
    losses = closed[~closed["is_win"]]

    total_fees = closed["fee_open_cost"].fillna(0).sum() + closed["fee_close_cost"].fillna(0).sum()

    win_rate = len(wins) / len(closed) * 100 if len(closed) > 0 else 0
    avg_win = wins["net_profit"].mean() if len(wins) > 0 else 0
    avg_loss = losses["net_profit"].mean() if len(losses) > 0 else 0

    gross_profit = wins["net_profit"].sum()
    gross_loss = abs(losses["net_profit"].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    total_pnl = closed["net_profit"].sum()
    expectancy = closed["net_profit"].mean() if len(closed) > 0 else 0

    # Drawdown — running P&L
    closed_sorted = closed.sort_values("close_date").reset_index(drop=True)
    closed_sorted["cum_pnl"] = closed_sorted["net_profit"].cumsum()
    closed_sorted["peak"] = closed_sorted["cum_pnl"].cummax()
    closed_sorted["drawdown"] = closed_sorted["cum_pnl"] - closed_sorted["peak"]
    max_drawdown = closed_sorted["drawdown"].min()

    return {
        "total_trades": len(closed),
        "open_trades": len(open_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 2),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else "inf",
        "total_pnl": round(total_pnl, 4),
        "expectancy": round(expectancy, 4),
        "total_fees": round(total_fees, 4),
        "max_drawdown": round(max_drawdown, 4),
        "median_win": round(wins["net_profit"].median(), 4) if len(wins) > 0 else 0,
        "median_loss": round(losses["net_profit"].median(), 4) if len(losses) > 0 else 0,
        "pct_25_win": round(wins["net_profit"].quantile(0.25), 4) if len(wins) > 0 else 0,
        "pct_75_win": round(wins["net_profit"].quantile(0.75), 4) if len(wins) > 0 else 0,
        "largest_win": round(wins["net_profit"].max(), 4) if len(wins) > 0 else 0,
        "largest_loss": round(losses["net_profit"].min(), 4) if len(losses) > 0 else 0,
        "avg_holding_minutes": round(closed["holding_minutes"].mean(), 1),
        "avg_mfe": round(closed["mfe_pct"].mean(), 3),
        "avg_mae": round(closed["mae_pct"].mean(), 3),
        "avg_mfe_winners": round(wins["mfe_pct"].mean(), 3) if len(wins) > 0 else 0,
        "avg_mfe_losers": round(losses["mfe_pct"].mean(), 3) if len(losses) > 0 else 0,
        "avg_mae_winners": round(wins["mae_pct"].mean(), 3) if len(wins) > 0 else 0,
        "avg_mae_losers": round(losses["mae_pct"].mean(), 3) if len(losses) > 0 else 0,
        "be_win_rate": round(1 / (1 + abs(avg_loss / avg_win)), 4) * 100 if avg_loss != 0 else 100,
    }

# ─── Per-pair stats ────────────────────────────────────────────────────────────

def pair_stats(df: pd.DataFrame) -> pd.DataFrame:
    closed = df[df["is_open"] == 0].copy()
    rows = []
    for pair, g in closed.groupby("pair"):
        wins = g[g["is_win"]]
        losses = g[~g["is_win"]]
        wr = len(wins) / len(g) * 100 if len(g) > 0 else 0
        avg_win = wins["net_profit"].mean() if len(wins) > 0 else 0
        avg_loss = losses["net_profit"].mean() if len(losses) > 0 else 0
        pf = wins["net_profit"].sum() / abs(losses["net_profit"].sum()) if len(losses) > 0 and losses["net_profit"].sum() != 0 else float("inf")
        rows.append({
            "pair": pair,
            "trades": len(g),
            "win_rate_pct": round(wr, 2),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "net_pnl": round(g["net_profit"].sum(), 4),
            "expectancy": round(g["net_profit"].mean(), 4),
            "profit_factor": round(pf, 3) if pf != float("inf") else "inf",
            "avg_holding_min": round(g["holding_minutes"].mean(), 1),
            "avg_mfe_pct": round(g["mfe_pct"].mean(), 3),
            "avg_mae_pct": round(g["mae_pct"].mean(), 3),
        })
    return pd.DataFrame(rows).sort_values("net_pnl", ascending=False)

# ─── Per confidence bucket stats ───────────────────────────────────────────────

def bucket_stats(df: pd.DataFrame) -> pd.DataFrame:
    closed = df[df["is_open"] == 0].copy()
    rows = []
    for bucket in ["< 0.55", "0.55–0.60", "0.60–0.70", "0.70–0.80", "0.80–0.90", "0.90+", "untagged"]:
        g = closed[closed["conf_bucket"] == bucket]
        if len(g) == 0:
            continue
        wins = g[g["is_win"]]
        losses = g[~g["is_win"]]
        wr = len(wins) / len(g) * 100 if len(g) > 0 else 0
        avg_win = wins["net_profit"].mean() if len(wins) > 0 else 0
        avg_loss = losses["net_profit"].mean() if len(losses) > 0 else 0
        pf = wins["net_profit"].sum() / abs(losses["net_profit"].sum()) if len(losses) > 0 and losses["net_profit"].sum() != 0 else float("inf")
        rows.append({
            "bucket": bucket,
            "trades": len(g),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(wr, 2),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "net_pnl": round(g["net_profit"].sum(), 4),
            "expectancy": round(g["net_profit"].mean(), 4),
            "profit_factor": round(pf, 3) if pf != float("inf") else "inf",
            "avg_mfe_pct": round(g["mfe_pct"].mean(), 3),
            "avg_mae_pct": round(g["mae_pct"].mean(), 3),
        })
    return pd.DataFrame(rows)

# ─── Per exit reason stats ─────────────────────────────────────────────────────

def exit_reason_stats(df: pd.DataFrame) -> pd.DataFrame:
    closed = df[df["is_open"] == 0].copy()
    rows = []
    for reason, g in closed.groupby("exit_reason"):
        wins = g[g["is_win"]]
        wr = len(wins) / len(g) * 100 if len(g) > 0 else 0
        rows.append({
            "exit_reason": reason,
            "trades": len(g),
            "win_rate_pct": round(wr, 2),
            "net_pnl": round(g["net_profit"].sum(), 4),
            "expectancy": round(g["net_profit"].mean(), 4),
            "avg_holding_min": round(g["holding_minutes"].mean(), 1),
        })
    return pd.DataFrame(rows).sort_values("net_pnl", ascending=False)

# ─── Build report ──────────────────────────────────────────────────────────────

def build_report(df: pd.DataFrame, label: str) -> dict:
    closed = df[df["is_open"] == 0]
    ov = overall_stats(df)
    pairs = pair_stats(df)
    buckets = bucket_stats(df)
    exits = exit_reason_stats(df)

    report_date = datetime.now().strftime("%Y-%m-%d")
    version = label or "combined"

    # ─ Markdown report ─────────────────────────────────────────────────────────
    md_lines = [
        f"# LeahAI Strategy Expectancy Report",
        f"**Label:** {label or 'all-databases'}",
        f"**Generated:** {report_date} {datetime.now().strftime('%H:%M:%S')}",
        f"**Source DBs:** {', '.join(df['source_db'].unique())}",
        "",
        "---",
        "",
        "## Overall Statistics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total closed trades | {ov['total_trades']} |",
        f"| Open trades | {ov['open_trades']} |",
        f"| Wins / Losses | {ov['wins']} / {ov['losses']} |",
        f"| **Win rate** | **{ov['win_rate_pct']}%** |",
        f"| Avg winner | ${ov['avg_win']} |",
        f"| Avg loser | ${ov['avg_loss']} |",
        f"| **Net avg win** | ${ov['avg_win']} |",
        f"| **Net avg loss** | ${ov['avg_loss']} |",
        f"| Median winner | ${ov['median_win']} |",
        f"| Median loser | ${ov['median_loss']} |",
        f"| 25th pct win | ${ov['pct_25_win']} |",
        f"| 75th pct win | ${ov['pct_75_win']} |",
        f"| Largest winner | ${ov['largest_win']} |",
        f"| Largest loser | ${ov['largest_loss']} |",
        f"| **Profit factor** | **{ov['profit_factor']}** |",
        f"| **Total P&L** | **${ov['total_pnl']}** |",
        f"| **Expectancy/trade** | **${ov['expectancy']}** |",
        f"| Total fees paid | ${ov['total_fees']} |",
        f"| Max drawdown | ${ov['max_drawdown']} |",
        f"| Avg holding time | {ov['avg_holding_minutes']} min |",
        f"| **Breakeven WR** | **{ov['be_win_rate']}%** |",
        "",
        "### MFE / MAE Analysis",
        "",
        "| Metric | All Trades | Winners | Losers |",
        "|--------|-----------|---------|--------|",
        f"| Avg MFE % | {ov['avg_mfe']}% | {ov['avg_mfe_winners']}% | {ov['avg_mfe_losers']}% |",
        f"| Avg MAE % | {ov['avg_mae']}% | {ov['avg_mae_winners']}% | {ov['avg_mae_losers']}% |",
        "",
        "> **MFE interpretation:** Max Favorable Excursion — how much the price moved in your favor after entry.",
        "> **MAE interpretation:** Max Adverse Excursion — how much the price moved against you before exit.",
        "",
        "### Key Questions from MFE/MAE",
        "",
        "- If **avg MFE >> avg win**, profit targets are too tight — you're leaving money on the table.",
        "- If **avg MAE ≈ stoploss distance**, stops are too tight and firing before reversion completes.",
        "- If **avg MAE >> avg loss**, the stop was hit but price reverted immediately after — classic stop hunting.",
        "",
        "---",
        "",
        "## Per-Pair Breakdown",
        "",
        "| Pair | Trades | Win Rate | Avg Win | Avg Loss | Net P&L | Expectancy | Profit Factor |",
        "|------|--------|----------|---------|----------|---------|------------|---------------|",
    ]

    for _, r in pairs.iterrows():
        md_lines.append(
            f"| {r['pair']} | {r['trades']} | {r['win_rate_pct']}% | "
            f"${r['avg_win']} | ${r['avg_loss']} | ${r['net_pnl']} | "
            f"${r['expectancy']} | {r['profit_factor']} |"
        )

    md_lines += [
        "",
        "---",
        "",
        "## Per Confidence Bucket",
        "",
        "| Bucket | Trades | Wins | Losses | Win Rate | Avg Win | Avg Loss | Net P&L | Expectancy |",
        "|--------|--------|------|--------|----------|---------|----------|---------|------------|",
    ]

    for _, r in buckets.iterrows():
        md_lines.append(
            f"| {r['bucket']} | {r['trades']} | {r['wins']} | {r['losses']} | "
            f"{r['win_rate_pct']}% | ${r['avg_win']} | ${r['avg_loss']} | "
            f"${r['net_pnl']} | ${r['expectancy']} |"
        )

    md_lines += [
        "",
        "> **If win rate increases with confidence bucket → model is well-calibrated.**",
        "> **If highest-confidence bucket has worst win rate → model is anti-calibrated.**",
        "",
        "---",
        "",
        "## Per Exit Reason",
        "",
        "| Exit Reason | Trades | Win Rate | Net P&L | Expectancy | Avg Hold (min) |",
        "|-------------|--------|----------|---------|------------|----------------|",
    ]

    for _, r in exits.iterrows():
        md_lines.append(
            f"| {r['exit_reason']} | {r['trades']} | {r['win_rate_pct']}% | "
            f"${r['net_pnl']} | ${r['expectancy']} | {r['avg_holding_min']} |"
        )

    md_lines += [
        "",
        "---",
        "",
        "## Exit Reason Interpretation",
        "",
        "- **roi** — ROI target hit. Check MFE: if MFE >> avg_win, targets are too conservative.",
        "- **stop_loss** — Stop triggered. Check MAE: if MAE is close to stop distance, reversion happened after.",
        "- **trailing_stop** — Trailing stop triggered.",
        "- **force_entry** / **partial** — Manual or partial exit.",
        "",
        "---",
        "",
        "## Recommendations",
        "",
        "Based on this report:",
        "",
    ]

    # Auto-generate recommendations
    if ov["expectancy"] < 0:
        md_lines.append(f"> ⚠️ **Structurally negative expectancy (${ov['expectancy']}/trade).** Fix payoff structure before model changes.")
    if ov["be_win_rate"] > ov["win_rate_pct"]:
        gap = ov["be_win_rate"] - ov["win_rate_pct"]
        md_lines.append(f"> ⚠️ **Win rate gap: {gap:.1f}pp below breakeven WR ({ov['be_win_rate']}%).** Reduce loss size or widen ROI targets.")
    if len(buckets) > 1 and not buckets.empty:
        try:
            high_conf = buckets[buckets["bucket"] >= "0.80"]["expectancy"].mean()
            low_conf = buckets[buckets["bucket"] < "0.70"]["expectancy"].mean()
            if high_conf < low_conf:
                md_lines.append("> ⚠️ **Model is anti-calibrated: higher confidence → lower expectancy.** Do not trust model confidence until fixed.")
        except Exception:
            pass
    if ov["avg_mae"] > 3.0:
        md_lines.append(f"> ⚠️ **MAE is {ov['avg_mae']}% — stops may be too tight.** Consider widening stop or using dynamic stop logic.")
    if ov["avg_mfe"] > ov["avg_win"] * 3:
        md_lines.append(f"> ⚠️ **MFE ({ov['avg_mfe']}%) is 3x+ larger than avg_win.** Profit targets may be too tight.")
    if not buckets.empty and "untagged" in buckets["bucket"].values:
        untagged_pct = buckets[buckets["bucket"] == "untagged"]["trades"].values[0] / ov["total_trades"] * 100
        md_lines.append(f"> ⚠️ **{untagged_pct:.0f}% of trades are untagged.** enter_tag not populated — populate it to enable bucket analysis.")

    md_lines += [
        "",
        "---",
        "",
        f"*Report generated by analyze_expectancy.py — LeahAI Strategy Expectancy Report*",
        f"*Source: {', '.join(df['source_db'].unique())}*",
    ]

    md_text = "\n".join(md_lines)

    # ─ CSV exports ─────────────────────────────────────────────────────────────
    closed_export = closed[[
        "id", "pair", "is_open", "open_rate", "close_rate", "net_profit",
        "fee_open_cost", "fee_close_cost", "stake_amount", "enter_tag",
        "exit_reason", "open_date", "close_date", "holding_minutes",
        "mfe_pct", "mae_pct", "is_win", "confidence", "conf_bucket",
        "max_rate", "min_rate", "strategy", "source_db"
    ]].copy()

    pairs_csv = pairs.to_csv(index=False)
    buckets_csv = buckets.to_csv(index=False)
    exits_csv = exits.to_csv(index=False)
    overall_csv = pd.DataFrame([ov]).to_csv(index=False)

    return {
        "markdown": md_text,
        "overall": ov,
        "pairs": pairs,
        "buckets": buckets,
        "exits": exits,
        "closed_export": closed_export,
        "pairs_csv": pairs_csv,
        "buckets_csv": buckets_csv,
        "exits_csv": exits_csv,
        "overall_csv": overall_csv,
    }

# ─── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(args.output_dir, exist_ok=True)

    all_dfs = []
    for db_path in args.dbs:
        df = load_trades(db_path)
        if df is not None:
            all_dfs.append(df)

    if not all_dfs:
        print("No trade data found. Exiting.")
        sys.exit(1)

    combined = pd.concat(all_dfs, ignore_index=True)
    db_names = "_".join(os.path.basename(d) for d in args.dbs)
    label_str = f"_{args.label}" if args.label else ""
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    report = build_report(combined, args.label or "combined")

    # Save outputs
    out_base = f"{args.output_dir}/lea_expectancy_{label_str}_{date_str}"

    md_path = f"{out_base}.md"
    csv_trades_path = f"{out_base}_trades.csv"
    csv_pairs_path = f"{out_base}_pairs.csv"
    csv_buckets_path = f"{out_base}_buckets.csv"
    csv_exits_path = f"{out_base}_exits.csv"
    csv_overall_path = f"{out_base}_overall.csv"

    with open(md_path, "w") as f:
        f.write(report["markdown"])

    report["closed_export"].to_csv(csv_trades_path, index=False)
    report["pairs"].to_csv(csv_pairs_path, index=False)
    report["buckets"].to_csv(csv_buckets_path, index=False)
    report["exits"].to_csv(csv_exits_path, index=False)
    report["overall_csv"] = pd.DataFrame([report["overall"]]).to_csv(index=False)
    pd.DataFrame([report["overall"]]).to_csv(csv_overall_path, index=False)

    print(f"\n{'='*60}")
    print("LEAHAI STRATEGY EXPECTANCY REPORT")
    print(f"{'='*60}")
    print(f"\n{'OVERALL':=^40}")
    ov = report["overall"]
    print(f"  Trades:        {ov['total_trades']} closed, {ov['open_trades']} open")
    print(f"  Win rate:      {ov['win_rate_pct']}%")
    print(f"  Avg win:       ${ov['avg_win']}")
    print(f"  Avg loss:      ${ov['avg_loss']}")
    print(f"  Profit factor: {ov['profit_factor']}")
    print(f"  Total P&L:     ${ov['total_pnl']}")
    print(f"  Expectancy:    ${ov['expectancy']}/trade")
    print(f"  Breakeven WR:  {ov['be_win_rate']}%")
    print(f"  Total fees:    ${ov['total_fees']}")
    print(f"  Max drawdown:  ${ov['max_drawdown']}")
    print(f"  MFE:           {ov['avg_mfe']}% (winners: {ov['avg_mfe_winners']}%, losers: {ov['avg_mfe_losers']}%)")
    print(f"  MAE:           {ov['avg_mae']}% (winners: {ov['avg_mae_winners']}%, losers: {ov['avg_mae_losers']}%)")

    print(f"\n{'PER-PAIR':=^40}")
    print(report["pairs"][["pair","trades","win_rate_pct","net_pnl","expectancy","profit_factor"]].to_string(index=False))

    print(f"\n{'PER-CONFIDENCE-BUCKET':=^40}")
    print(report["buckets"][["bucket","trades","win_rate_pct","net_pnl","expectancy"]].to_string(index=False))

    print(f"\n{'PER-EXIT-REASON':=^40}")
    print(report["exits"][["exit_reason","trades","win_rate_pct","net_pnl","expectancy"]].to_string(index=False))

    print(f"\n{'OUTPUTS':=^40}")
    print(f"  Markdown: {md_path}")
    print(f"  Trades CSV: {csv_trades_path}")
    print(f"  Pairs CSV: {csv_pairs_path}")
    print(f"  Buckets CSV: {csv_buckets_path}")
    print(f"  Exits CSV: {csv_exits_path}")
    print(f"  Overall CSV: {csv_overall_path}")
    print()
