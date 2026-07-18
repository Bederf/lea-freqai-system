#!/usr/bin/env python3
"""
E002 — Expansion Quality Filtering
===================================
Systematic sweep of expansion quality filters to determine which predicted
volatility expansions are large enough to be economically tradable.

Filters tested:
  1. atr14 percentile rank (0, 20, 40, 60, 80, 100)
  2. vol_ratio_20 threshold (0.9, 1.0, 1.1, 1.2, 1.3, 1.5)
  3. hl_range percentile rank (0, 20, 40, 60, 80)
  4. %atr14_rel threshold (0.0, 0.5, 1.0, 1.5, 2.0)
  5. atr14 raw (0.005, 0.010, 0.015, 0.020, 0.025)

Baseline (no filter): threshold 0.55
Best filter + 0.55
Best filter + 0.65

Output: per-filter summary table with net profit, expectancy, PF, win rate, trade count, drawdown.
"""

import gc, joblib, pickle, sys, warnings
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
warnings.filterwarnings("ignore")

DATA_DIR   = Path("/freqtrade/user_data/data/binance")
MODEL_DIR  = Path("/freqtrade/user_data/models")
FOLD_DATA  = Path("/freqtrade/user_data/reports/experiments/expE_BTC_20260711_211246.csv")
OUTPUT_DIR = Path("/freqtrade/user_data/reports/e002")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, "/freqtrade/user_data")
from retrain_15f_classifier import build_features, FEATURE_COLS

PAIRS      = ["BTC", "ETH", "SOL", "LINK"]
PAIR_FILES = {"BTC": "BTC_USDT", "ETH": "ETH_USDT", "SOL": "SOL_USDT", "LINK": "LINK_USDT"}
TRAIN_N    = 8640
TEST_N     = 2016
FEE_PCT    = 0.001

ROI_LADDER   = [(0, 0.05), (30, 0.03), (60, 0.02), (120, 0.01)]
STOPLOSS_PCT = -0.05
TIME_EXIT_HRS = 6.0
EMA_PERIOD    = 50
BASE_THRESH   = 0.55


# ─── Filter definitions ────────────────────────────────────────────────────────

FILTERS = [
    # (name, feature, type, values)
    # Percentile rank filters
    ("atr14_pct",     "atr14",       "pct",    [0, 20, 40, 60, 80, 100]),
    ("hl_range_pct",  "hl_range",     "pct",    [0, 20, 40, 60, 80]),
    # Threshold filters
    ("vol_r20",       "vol_ratio_20", "thresh", [0.9, 1.0, 1.1, 1.2, 1.3, 1.5]),
    ("atr_pct_rel",   "%atr14_rel",   "thresh", [0.0, 0.5, 1.0, 1.5, 2.0]),
    ("atr14_raw",     "atr14",        "raw",    [0.005, 0.010, 0.015, 0.020, 0.025]),
]

# All filter configs for the sweep
FILTER_CONFIGS = []
for name, feat, ftype, values in FILTERS:
    for val in values:
        FILTER_CONFIGS.append({"name": name, "feature": feat, "type": ftype, "value": val})
# Add baseline (no filter)
FILTER_CONFIGS.append({"name": "baseline", "feature": None, "type": None, "value": None})


# ─── Helpers ──────────────────────────────────────────────────────────────────

def compute_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def load_pair_data(pair, fold_end, test_n=TEST_N):
    pf = PAIR_FILES[pair]
    feather = DATA_DIR / f"{pf}-5m.feather"
    if not feather.exists():
        return None

    df = pd.read_feather(feather).rename(columns={"date": "open_time"})
    df = df.sort_values("open_time").reset_index(drop=True)

    fold_end_ts = pd.to_datetime(fold_end)
    if fold_end_ts.tz is None:
        fold_end_ts = fold_end_ts.tz_localize("UTC")
    split_idx = df[df["open_time"] >= fold_end_ts].index
    if len(split_idx) == 0:
        return None
    si = split_idx[0]
    test_end = min(si + test_n, len(df))
    if test_end - si < 100:
        return None

    df = df.iloc[si:test_end].copy().reset_index(drop=True)
    df = build_features(df)
    feat_df = df[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(0)

    model, scaler = load_model(pair)
    if model is None or scaler is None:
        return None
    try:
        probs = model.predict_proba(scaler.transform(feat_df.values))[:, 1]
    except Exception:
        return None

    df["probability"] = probs
    df["ema_50"] = compute_ema(df["close"], EMA_PERIOD)

    # Compute percentile rank for atr14 and hl_range (over the test window)
    df["atr14_pct_rank"] = df["atr14"].rank(pct=True, ascending=True) * 100
    df["hl_range_pct_rank"] = df["hl_range"].rank(pct=True, ascending=True) * 100

    return df


def load_btc_trend(fold_end, test_n=TEST_N):
    feather = DATA_DIR / "BTC_USDT-5m.feather"
    if not feather.exists():
        return None
    btc = pd.read_feather(feather).rename(columns={"date": "open_time"})
    btc = btc.sort_values("open_time").reset_index(drop=True)
    fold_end_ts = pd.to_datetime(fold_end)
    if fold_end_ts.tz is None:
        fold_end_ts = fold_end_ts.tz_localize("UTC")
    split_idx = btc[btc["open_time"] >= fold_end_ts].index
    if len(split_idx) == 0:
        return None
    si = split_idx[0]
    test_end = min(si + test_n, len(btc))
    if test_end - si < 100:
        return None
    btc = btc.iloc[si:test_end].copy().reset_index(drop=True)
    btc["btc_trend"] = btc["close"].pct_change(5)
    return btc[["open_time", "btc_trend"]]


def load_model(pair):
    short = pair
    model_path  = MODEL_DIR / f"leah_v4_4_{short}_xgb_clf.pkl"
    scaler_path = MODEL_DIR / f"leah_v4_4_{short}_xgb_clf_scaler.pkl"
    model = scaler = None
    if model_path.exists():
        with open(model_path, "rb") as f:
            model = pickle.load(f)
    if scaler_path.exists():
        with open(scaler_path, "rb") as f:
            scaler = joblib.load(f)
    return model, scaler


def load_folds():
    import csv
    folds = []
    with open(FOLD_DATA) as f:
        for row in csv.DictReader(f):
            if row["model"] == "C (15 stable)":
                folds.append({"fold_end": row["fold_end"]})
    return folds


# ─── Filter application ───────────────────────────────────────────────────────

def passes_filter(row, fcfg):
    """Return True if row passes the expansion quality filter."""
    if fcfg["name"] == "baseline":
        return True

    feat = fcfg["feature"]
    ftype = fcfg["type"]
    val   = fcfg["value"]

    if feat not in row.index:
        return True  # skip if feature missing

    v = row[feat]

    if ftype == "pct":
        # row["atr14_pct_rank"] or row["hl_range_pct_rank"]
        pct_col = feat + "_pct_rank"
        if pct_col in row.index:
            return row[pct_col] >= val
        return True

    elif ftype == "thresh":
        return v >= val

    elif ftype == "raw":
        return v >= val

    return True


# ─── Core simulation ──────────────────────────────────────────────────────────

def simulate_trades(pair_df, btc_df, threshold, fcfg):
    """Simulate trades with optional expansion quality filter. Returns list of trade dicts."""
    # Merge BTC trend
    df = pair_df.copy()
    if btc_df is not None:
        df["btc_trend"] = btc_df["btc_trend"].reindex(df.index, method="ffill").fillna(0)
    else:
        df["btc_trend"] = 0.0

    n = len(df)
    trades = []
    in_trade = False
    entry_idx = entry_price = entry_prob = entry_time = None

    for i in range(n):
        row = df.iloc[i]

        if not in_trade:
            # Entry gates
            if row["probability"] < threshold:
                continue
            if row.get("btc_trend", 0) < 0.002:
                continue
            if row["ema_50"] > 0 and row["close"] <= row["ema_50"]:
                continue
            # Expansion quality filter
            if not passes_filter(row, fcfg):
                continue

            in_trade = True
            entry_price = float(row["close"])
            entry_prob  = float(row["probability"])
            entry_time  = row["open_time"]

        else:
            current_price = float(row["close"])
            current_time  = row["open_time"]

            try:
                entry_t = entry_time
                curr_t  = current_time
                if hasattr(entry_t, 'tz') and entry_t.tz is None:
                    entry_t = entry_t.tz_localize("UTC")
                if hasattr(curr_t, 'tz') and curr_t.tz is None:
                    curr_t = curr_t.tz_localize("UTC")
                dt_min = (curr_t - entry_t).total_seconds() / 60.0
            except Exception:
                dt_min = 0.0

            pct_ret = (current_price - entry_price) / entry_price
            exited = False
            exit_reason = None

            # ROI
            for cutoff_min, roi_pct in reversed(ROI_LADDER):
                if dt_min >= cutoff_min and pct_ret >= roi_pct:
                    exited = True
                    exit_reason = f"roi_{roi_pct}"
                    break
            # Stoploss
            if not exited and pct_ret <= STOPLOSS_PCT:
                exited = True
                exit_reason = "stoploss"
            # Time exit
            if not exited and dt_min > TIME_EXIT_HRS * 60 and pct_ret < 0:
                exited = True
                exit_reason = "time_exit_6h_negative"

            if exited:
                gross_ret = (current_price - entry_price) / entry_price
                net_pnl = gross_ret - FEE_PCT * 2
                conf_mult = np.clip(1.0 + (entry_prob - threshold) * 2.5, 0.5, 1.5)
                net_pnl *= conf_mult
                trades.append({
                    "threshold": threshold,
                    "filter": fcfg["name"],
                    "filter_value": fcfg["value"],
                    "duration_min": dt_min,
                    "gross_return": gross_ret,
                    "net_pnl": net_pnl,
                    "is_win": net_pnl > 0,
                    "exit_reason": exit_reason,
                    "probability": entry_prob,
                })
                in_trade = False

    return trades


# ─── Run ─────────────────────────────────────────────────────────────────────

import pandas as pd
import numpy as np

def run():
    folds = load_folds()
    print(f"E002 — Expansion Quality Filtering")
    print(f"Folds: {len(folds)}  Pairs: {PAIRS}  Filters: {len(FILTER_CONFIGS)}")
    print()

    # Pre-load all pair+fold data ONCE
    print("Loading data...")
    pair_data = {}  # (pair, fold_end) -> (pair_df, btc_df)
    for pair in PAIRS:
        for fold in folds:
            pair_df = load_pair_data(pair, fold["fold_end"])
            btc_df  = load_btc_trend(fold["fold_end"])
            if pair_df is not None:
                pair_data[(pair, fold["fold_end"])] = (pair_df, btc_df)
        print(f"  {pair}: {sum(1 for k in pair_data if k[0] == pair)} folds loaded")

    print(f"\nSimulating {len(FILTER_CONFIGS)} filter configs across all pairs + folds...")

    # Run configs in order; each config iterates over pre-loaded data
    # Batch: run ALL configs that share the same data simultaneously
    results_by_filter = defaultdict(list)

    for fidx, fcfg in enumerate(FILTER_CONFIGS):
        filter_tag = f"{fcfg['name']}_{fcfg['value']}" if fcfg['name'] != 'baseline' else 'baseline'
        print(f"  [{fidx+1}/{len(FILTER_CONFIGS)}] {filter_tag}", end="  ", flush=True)

        for (pair, fold_end), (pair_df, btc_df) in pair_data.items():
            for threshold in [BASE_THRESH, 0.65]:
                trades = simulate_trades(pair_df, btc_df, threshold, fcfg)
                for t in trades:
                    t["pair"] = pair
                    t["fold_end"] = fold_end
                results_by_filter[filter_tag].extend(trades)
                results_by_filter[filter_tag + f"_t{threshold}"].extend([t for t in trades if t["threshold"] == threshold])

        # Count trades for this filter
        n = len(results_by_filter[filter_tag])
        print(f"→ {n} trades")
        gc.collect()

    # Flatten all trades from results_by_filter
    all_trades = []
    for fcfg in FILTER_CONFIGS:
        filter_tag = f"{fcfg['name']}_{fcfg['value']}" if fcfg['name'] != 'baseline' else 'baseline'
        all_trades.extend(results_by_filter[filter_tag])

    df = pd.DataFrame(all_trades)
    print(f"\nTotal trade records: {len(df)}")

    # ─── Aggregate per filter+threshold ────────────────────────────────────────
    print("\n" + "=" * 80)
    print("E002 — EXPANSION QUALITY FILTER RESULTS")
    print("=" * 80)

    records = []
    for fcfg in FILTER_CONFIGS:
        filter_tag = f"{fcfg['name']}_{fcfg['value']}" if fcfg['name'] != 'baseline' else 'baseline'
        for threshold in [BASE_THRESH, 0.65]:
            key = (filter_tag, threshold)
            sub = df[(df["filter"] == fcfg["name"] if fcfg["name"] != "baseline" else df["filter"] == "baseline") & (df["threshold"] == threshold)]
            # Fix: use correct filter match
            if fcfg["name"] == "baseline":
                sub = df[(df["filter"] == "baseline") & (df["threshold"] == threshold)]
            else:
                sub = df[(df["filter"] == fcfg["name"]) & (df["filter_value"] == fcfg["value"]) & (df["threshold"] == threshold)]

            n = len(sub)
            if n == 0:
                continue

            wins = int((sub["net_pnl"] > 0).sum())
            wr   = wins / n * 100
            tp   = float(sub["net_pnl"].sum())
            gp   = float(sub.loc[sub["net_pnl"] > 0, "net_pnl"].sum())
            gl   = abs(float(sub.loc[sub["net_pnl"] <= 0, "net_pnl"].sum()))
            pf   = gp / max(gl, 1e-9)
            exp  = tp / n
            cum  = np.cumsum(sub.sort_values("fold_end")["net_pnl"].values)
            peak = np.maximum.accumulate(cum)
            dd   = cum - peak
            max_dd_pct = abs(dd.min()) / (peak.max() + 1e-9) * 100 if peak.max() > 0 else 0
            days = len(folds) * 7
            cagr = ((1 + tp) ** (365 / days) - 1) * 100 if days > 0 else 0

            # Exit breakdown
            te_n = int((sub["exit_reason"] == "time_exit_6h_negative").sum())
            roi_n = int(sub["exit_reason"].str.startswith("roi_").sum())
            sl_n  = int((sub["exit_reason"] == "stoploss").sum())

            records.append({
                "filter": filter_tag,
                "filter_name": fcfg["name"],
                "filter_value": fcfg["value"],
                "threshold": threshold,
                "trades": n,
                "win_rate": round(wr, 1),
                "total_pnl": round(tp, 4),
                "profit_factor": round(pf, 3),
                "expectancy": round(exp, 5),
                "max_dd_pct": round(max_dd_pct, 1),
                "cagr": round(cagr, 1),
                "time_exit_n": te_n,
                "time_exit_pct": round(te_n/n*100, 1),
                "roi_n": roi_n,
                "stoploss_n": sl_n,
            })

    summary = pd.DataFrame(records)

    # Print results table
    print(f"\n{'Filter':<20} {'Thresh':>6} {'n':>5} {'WR%':>6} {'PF':>6} {'E':>8} {'DD%':>7} {'CAGR%':>7} {'TE%':>5}")
    print("-" * 80)
    for _, r in summary.sort_values(["threshold", "expectancy"], ascending=[True, False]).iterrows():
        print(
            f"{r['filter']:<20} "
            f"{r['threshold']:>6.2f} "
            f"{int(r['trades']):>5} "
            f"{r['win_rate']:>6.1f} "
            f"{r['profit_factor']:>6.3f} "
            f"{r['expectancy']:>8.5f} "
            f"{r['max_dd_pct']:>7.1f} "
            f"{r['cagr']:>7.1f} "
            f"{r['time_exit_pct']:>5.1f}"
        )

    # ─── Best per threshold ────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("BEST FILTER PER THRESHOLD (by expectancy)")
    print("=" * 80)
    for thresh in [BASE_THRESH, 0.65]:
        sub = summary[summary["threshold"] == thresh].sort_values("expectancy", ascending=False)
        best = sub.iloc[0] if len(sub) > 0 else None
        if best is not None:
            print(f"\n  Threshold {thresh}:")
            print(f"    Best filter: {best['filter']} (value={best['filter_value']})")
            print(f"    Trades: {int(best['trades'])}  WR: {best['win_rate']}%  PF: {best['profit_factor']}")
            print(f"    Expectancy: {best['expectancy']:+.5f}  CAGR: {best['cagr']}%  DD: {best['max_dd_pct']}%")
            print(f"    Time-exit %: {best['time_exit_pct']}%")

    # ─── Recommendation ───────────────────────────────────────────────────────
    baseline_55 = summary[(summary["filter"] == "baseline") & (summary["threshold"] == BASE_THRESH)]
    baseline_65 = summary[(summary["filter"] == "baseline") & (summary["threshold"] == 0.65)]
    best_55 = summary[summary["threshold"] == BASE_THRESH].sort_values("expectancy", ascending=False).iloc[0]
    best_65 = summary[summary["threshold"] == 0.65].sort_values("expectancy", ascending=False).iloc[0]

    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)

    improvement_55 = best_55["expectancy"] - baseline_55["expectancy"].values[0] if len(baseline_55) else 0
    improvement_65 = best_65["expectancy"] - baseline_65["expectancy"].values[0] if len(baseline_65) else 0

    if best_55["expectancy"] > baseline_55["expectancy"].values[0] and best_65["expectancy"] > baseline_65["expectancy"].values[0]:
        recommendation = (
            f"Expansion quality filter improves both thresholds. "
            f"Best 0.55: {best_55['filter']} (E={best_55['expectancy']:+.5f}, +{improvement_55:+.5f} vs baseline). "
            f"Best 0.65: {best_65['filter']} (E={best_65['expectancy']:+.5f}, +{improvement_65:+.5f} vs baseline). "
            f"Recommend promoting best-performing combination to paper trading."
        )
    elif best_55["expectancy"] > baseline_55["expectancy"].values[0]:
        recommendation = (
            f"Expansion quality filter improves 0.55 only. "
            f"Best: {best_55['filter']} (E={best_55['expectancy']:+.5f}). "
            f"0.65 unchanged or worse. Promote best filter+threshold to paper trading."
        )
    elif best_65["expectancy"] > baseline_65["expectancy"].values[0]:
        recommendation = (
            f"Expansion quality filter improves 0.65 only. "
            f"Best: {best_65['filter']} (E={best_65['expectancy']:+.5f}). "
            f"Promote {best_65['filter']} + 0.65 to paper trading."
        )
    else:
        recommendation = (
            f"No filter improves expectancy over baseline for either threshold. "
            f"Best 0.55: {best_55['filter']} (E={best_55['expectancy']:+.5f}). "
            f"Best 0.65: {best_65['filter']} (E={best_65['expectancy']:+.5f}). "
            f"Consider architectural changes to exit rules before proceeding."
        )

    print(f"\n{recommendation}")

    # ─── Save ────────────────────────────────────────────────────────────────
    ts = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    summary_path = OUTPUT_DIR / f"E002_summary_{ts}.csv"
    trades_path  = OUTPUT_DIR / f"E002_trades_{ts}.csv"
    summary.to_csv(summary_path, index=False)
    df.to_csv(trades_path, index=False)
    print(f"\nSummary: {summary_path}")
    print(f"Trade log: {trades_path}")

    return summary, df, recommendation


if __name__ == "__main__":
    run()
