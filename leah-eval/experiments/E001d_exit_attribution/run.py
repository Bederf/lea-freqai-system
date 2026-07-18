#!/usr/bin/env python3
"""
E001d — Exit Attribution: MFE / MAE Analysis
=============================================
For each trade in the simulation, compute:
  - MFE: maximum favorable excursion (% profit reached at any point in trade)
  - MAE: maximum adverse excursion (% loss reached at any point in trade)
  - Time to MFE / MAE
  - Whether MFE crossed any ROI threshold before the actual exit fired
  - Whether the trade ever became profitable at all

Primary question: Did time-exit trades (60% of all trades) have profitable
opportunities that the current exits failed to capture?

Output:
  - Per-threshold summary of MFE/MAE metrics
  - Breakdown: time_exit vs roi vs stoploss
  - Missed opportunity analysis: trades where MFE > next_roi_threshold
"""

import gc, joblib, pickle, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

# Container paths
DATA_DIR   = Path("/freqtrade/user_data/data/binance")
MODEL_DIR  = Path("/freqtrade/user_data/models")
FOLD_DATA  = Path("/freqtrade/user_data/reports/experiments/expE_BTC_20260711_211246.csv")
OUTPUT_DIR = Path("/freqtrade/user_data/reports/e001d")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, "/freqtrade/user_data")
from retrain_15f_classifier import build_features, FEATURE_COLS

PAIRS      = ["BTC", "ETH", "SOL", "LINK"]
PAIR_FILES = {"BTC": "BTC_USDT", "ETH": "ETH_USDT", "SOL": "SOL_USDT", "LINK": "LINK_USDT"}
THRESHOLDS = [0.55, 0.65]
TRAIN_N    = 8640
TEST_N     = 2016
FEE_PCT    = 0.001

# ROI ladder — in ascending order so we can find "next threshold"
ROI_LADDER = [
    (0,    0.05),   # immediate: 5%
    (30,   0.03),   # 30min: 3%
    (60,   0.02),   # 60min: 2%
    (120,  0.01),   # 120min+: 1% (floor)
]
STOPLOSS_PCT   = -0.05
TIME_EXIT_HRS  = 6.0
EMA_PERIOD      = 50


# ─── Helpers ──────────────────────────────────────────────────────────────────

def compute_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def load_pair_data(pair, fold_end, test_n=TEST_N):
    """Load test-window candles + features + probabilities."""
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
    return df


def load_btc_trend(fold_end, test_n=TEST_N):
    """Load BTC trend series for the test window."""
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


# ─── Core simulation with MFE/MAE tracking ────────────────────────────────────

def simulate_with_mfe(pair_df, btc_df, threshold):
    """
    Simulate trades AND record MFE/MAE at every candle.
    Returns list of trade dicts with MFE/MAE metrics.
    """
    # Merge BTC trend
    if btc_df is not None:
        pair_df = pair_df.copy()
        pair_df["btc_trend"] = btc_df["btc_trend"].reindex(pair_df.index, method="ffill").fillna(0)
    else:
        pair_df = pair_df.copy()
        pair_df["btc_trend"] = 0.0

    n = len(pair_df)
    trades = []
    in_trade = False

    entry_idx = None
    entry_price = None
    entry_prob = None
    entry_time = None

    for i in range(n):
        row = pair_df.iloc[i]

        if not in_trade:
            # ── ENTRY GATES ───────────────────────────────────────────────
            if row["probability"] < threshold:
                continue
            if row.get("btc_trend", 0) < 0.002:
                continue
            if row["ema_50"] > 0 and row["close"] <= row["ema_50"]:
                continue

            in_trade = True
            entry_idx = i
            entry_price = float(row["close"])
            entry_prob = float(row["probability"])
            entry_time = row["open_time"]

            # Track MFE/MAE over the trade
            mfe = 0.0
            mae = 0.0
            mfe_time_min = 0
            mae_time_min = 0
            mfe_reached_threshold = None  # first ROI threshold crossed
            became_profitable = False
            first_profitable_time = None

        else:
            current_price = float(row["close"])
            current_time  = row["open_time"]
            high_price    = float(pair_df.iloc[i]["high"])
            low_price     = float(pair_df.iloc[i]["low"])

            # MFE / MAE from entry
            pct_ret = (current_price - entry_price) / entry_price
            high_ret = (high_price - entry_price) / entry_price
            low_ret  = (low_price  - entry_price) / entry_price

            if high_ret > mfe:
                mfe = high_ret
                # Time to MFE
                try:
                    entry_t = entry_time
                    curr_t  = current_time
                    if hasattr(entry_t, 'tz') and entry_t.tz is None:
                        entry_t = entry_t.tz_localize("UTC")
                    if hasattr(curr_t, 'tz') and curr_t.tz is None:
                        curr_t = curr_t.tz_localize("UTC")
                    mfe_time_min = (curr_t - entry_t).total_seconds() / 60.0
                except Exception:
                    mfe_time_min = 0

            if low_ret < mae:
                mae = low_ret
                try:
                    entry_t = entry_time
                    curr_t  = current_time
                    if hasattr(entry_t, 'tz') and entry_t.tz is None:
                        entry_t = entry_t.tz_localize("UTC")
                    if hasattr(curr_t, 'tz') and curr_t.tz is None:
                        curr_t = curr_t.tz_localize("UTC")
                    mae_time_min = (curr_t - entry_t).total_seconds() / 60.0
                except Exception:
                    mae_time_min = 0

            # Track profitability
            if pct_ret > 0 and not became_profitable:
                became_profitable = True
                try:
                    entry_t = entry_time
                    curr_t  = current_time
                    if hasattr(entry_t, 'tz') and entry_t.tz is None:
                        entry_t = entry_t.tz_localize("UTC")
                    if hasattr(curr_t, 'tz') and curr_t.tz is None:
                        curr_t = curr_t.tz_localize("UTC")
                    first_profitable_time = (curr_t - entry_t).total_seconds() / 60.0
                except Exception:
                    first_profitable_time = 0

            # Duration so far
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

            current_profit = pct_ret
            exited = False
            exit_reason = None
            exit_price = current_price

            # Exit 1: ROI ladder
            for cutoff_min, roi_pct in reversed(ROI_LADDER):
                if dt_min >= cutoff_min and current_profit >= roi_pct:
                    exited = True
                    exit_reason = f"roi_{roi_pct}"
                    break

            # Exit 2: Stoploss
            if not exited and current_profit <= STOPLOSS_PCT:
                exited = True
                exit_reason = "stoploss"

            # Exit 3: Time exit — if underwater after 6h
            if not exited and dt_min > TIME_EXIT_HRS * 60 and current_profit < 0:
                exited = True
                exit_reason = "time_exit_6h_negative"

            if exited:
                gross_ret = (exit_price - entry_price) / entry_price
                net_pnl = gross_ret - FEE_PCT * 2
                conf_mult = np.clip(1.0 + (entry_prob - threshold) * 2.5, 0.5, 1.5)
                net_pnl *= conf_mult

                # Did MFE cross any ROI threshold before exit?
                missed_thresholds = []
                for cutoff_min, roi_pct in ROI_LADDER:
                    if dt_min >= cutoff_min and mfe >= roi_pct and exit_reason != f"roi_{roi_pct}":
                        missed_thresholds.append((cutoff_min, roi_pct))

                # Was there an ROI threshold the trade MFE crossed but didn't exit on?
                missed_roi = len(missed_thresholds) > 0

                trades.append({
                    "threshold":        threshold,
                    "entry_time":       entry_time,
                    "exit_time":        current_time,
                    "duration_min":     dt_min,
                    "entry_price":      entry_price,
                    "exit_price":       exit_price,
                    "gross_return":     gross_ret,
                    "net_pnl":          net_pnl,
                    "is_win":           net_pnl > 0,
                    "exit_reason":      exit_reason,
                    "probability":       entry_prob,
                    "confidence_mult":   conf_mult,
                    # MFE/MAE
                    "mfe_pct":          mfe,
                    "mae_pct":          mae,
                    "mfe_time_min":     mfe_time_min,
                    "mae_time_min":     mae_time_min,
                    # Did it ever become profitable?
                    "became_profitable": became_profitable,
                    "first_profitable_time": first_profitable_time,
                    # Missed opportunity
                    "missed_roi":       missed_roi,
                    "missed_thresholds": str(missed_thresholds),
                })
                in_trade = False

    return trades


# ─── Run ─────────────────────────────────────────────────────────────────────

import pandas as pd
import numpy as np

def run():
    folds = load_folds()
    print(f"E001d — Exit Attribution (MFE/MAE)")
    print(f"Folds: {len(folds)}  Pairs: {PAIRS}  Thresholds: {THRESHOLDS}")
    print()

    all_trades = []

    for pair in PAIRS:
        print(f"── {pair} ──")
        for fold in folds:
            pair_df = load_pair_data(pair, fold["fold_end"])
            if pair_df is None:
                continue
            btc_df = load_btc_trend(fold["fold_end"])
            for thresh in THRESHOLDS:
                trades = simulate_with_mfe(pair_df, btc_df, thresh)
                for t in trades:
                    t["pair"] = pair
                    t["fold_end"] = fold["fold_end"]
                all_trades.extend(trades)
            gc.collect()

    print(f"\nTotal trades: {len(all_trades)}")

    df = pd.DataFrame(all_trades)

    # ── Print summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("E001d — EXIT ATTRIBUTION RESULTS")
    print("=" * 70)

    for thresh in THRESHOLDS:
        tdf = df[df["threshold"] == thresh]
        n = len(tdf)
        print(f"\n── Threshold {thresh} (n={n}) ──")
        print(f"  Exit reasons:")
        for reason, cnt in tdf["exit_reason"].value_counts().items():
            print(f"    {reason}: {cnt} ({cnt/n*100:.1f}%)")

        # MFE / MAE stats
        print(f"  MFE: mean={tdf['mfe_pct'].mean()*100:.2f}%  median={tdf['mfe_pct'].median()*100:.2f}%  p90={tdf['mfe_pct'].quantile(0.9)*100:.2f}%")
        print(f"  MAE: mean={tdf['mae_pct'].mean()*100:.2f}%  median={tdf['mae_pct'].median()*100:.2f}%  p90={tdf['mae_pct'].quantile(0.9)*100:.2f}%")

        # Did trades become profitable?
        profitable_pct = tdf["became_profitable"].mean() * 100
        print(f"  Became profitable at any point: {profitable_pct:.1f}%")

        # Missed ROI
        missed = tdf[tdf["missed_roi"] == True]
        print(f"  MFE crossed ROI threshold but didn't exit there: {len(missed)}/{n} ({len(missed)/n*100:.1f}%)")

    # ── Time-exit deep dive ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("TIME-EXIT DEEP DIVE (both thresholds)")
    print("=" * 70)

    te = df[df["exit_reason"] == "time_exit_6h_negative"]
    other = df[df["exit_reason"] != "time_exit_6h_negative"]

    for label, sub in [("TIME-EXIT trades", te), ("ROI/stoploss trades", other)]:
        if len(sub) == 0:
            continue
        print(f"\n── {label} (n={len(sub)}) ──")
        print(f"  MFE: mean={sub['mfe_pct'].mean()*100:.2f}%  median={sub['mfe_pct'].median()*100:.2f}%  p90={sub['mfe_pct'].quantile(0.9)*100:.2f}%")
        print(f"  MAE: mean={sub['mae_pct'].mean()*100:.2f}%  median={sub['mae_pct'].median()*100:.2f}%  p90={sub['mae_pct'].quantile(0.9)*100:.2f}%")
        print(f"  Became profitable: {sub['became_profitable'].mean()*100:.1f}%")
        print(f"  Missed ROI opportunity: {sub['missed_roi'].mean()*100:.1f}%")

    # ── Recommendation ─────────────────────────────────────────────────────
    te_pct = len(te) / len(df) * 100

    # For time-exit trades: what fraction had MFE > 1% (could have hit roi_0.01)?
    if len(te) > 0:
        te_mfe_above_1pct = (te["mfe_pct"] >= 0.01).mean() * 100
        te_mfe_above_2pct = (te["mfe_pct"] >= 0.02).mean() * 100
        te_ever_profitable = te["became_profitable"].mean() * 100
    else:
        te_mfe_above_1pct = te_mfe_above_2pct = te_ever_profitable = 0

    print(f"\n── Key Findings ──")
    print(f"  Time-exit share: {te_pct:.1f}% of all trades")
    print(f"  Time-exit trades that EVER became profitable: {te_ever_profitable:.1f}%")
    print(f"  Time-exit trades with MFE >= 1%: {te_mfe_above_1pct:.1f}%")
    print(f"  Time-exit trades with MFE >= 2%: {te_mfe_above_2pct:.1f}%")

    # Recommendation
    if te_ever_profitable < 20:
        conclusion = (
            "CONCLUSION: Most time-exit trades NEVER became profitable. "
            "The problem is the entry signal, not the exit rules. "
            "E001d recommends: do NOT shorten the timeout. Investigate entries first."
        )
    elif te_mfe_above_1pct > 50:
        conclusion = (
            "CONCLUSION: Most time-exit trades REACHED +1% profit but were not captured. "
            "The exit logic is leaving money on the table. "
            "E001d recommends: shorten time exit OR implement trailing stop OR add partial exits."
        )
    else:
        conclusion = (
            "CONCLUSION: Mixed signals. Some time-exit trades became profitable but MFE "
            "did not consistently cross ROI thresholds. Further diagnosis needed before changing exits."
        )

    print(f"\n{conclusion}")

    # ── Save CSV ───────────────────────────────────────────────────────────
    ts = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"E001d_trades_{ts}.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nTrade log: {csv_path}")

    # ── Summary table per threshold ─────────────────────────────────────────
    records = []
    for thresh in THRESHOLDS:
        tdf = df[df["threshold"] == thresh]
        te  = tdf[tdf["exit_reason"] == "time_exit_6h_negative"]
        n   = len(tdf)
        te_n = len(te)
        wins = int((tdf["net_pnl"] > 0).sum())
        wr   = wins / n * 100
        tp   = float(tdf["net_pnl"].sum())
        pf   = float(tdf.loc[tdf["net_pnl"] > 0, "net_pnl"].sum()) / max(abs(float(tdf.loc[tdf["net_pnl"] <= 0, "net_pnl"].sum())), 1e-9)
        exp  = tp / n

        records.append({
            "threshold":       thresh,
            "total_trades":    n,
            "wins":            wins,
            "win_rate_pct":    round(wr, 1),
            "total_pnl":       round(tp, 4),
            "profit_factor":   round(pf, 3),
            "expectancy":      round(exp, 5),
            "time_exit_n":     te_n,
            "time_exit_pct":   round(te_n/n*100, 1),
            "mfe_mean_pct":    round(tdf["mfe_pct"].mean()*100, 2),
            "mfe_median_pct":  round(tdf["mfe_pct"].median()*100, 2),
            "mfe_p90_pct":     round(tdf["mfe_pct"].quantile(0.9)*100, 2),
            "mae_mean_pct":    round(tdf["mae_pct"].mean()*100, 2),
            "became_profitable_pct": round(tdf["became_profitable"].mean()*100, 1),
            "missed_roi_pct":  round(tdf["missed_roi"].mean()*100, 1),
            "te_ever_profitable_pct": round(te["became_profitable"].mean()*100, 1) if te_n > 0 else 0,
            "te_mfe_above_1pct": round((te["mfe_pct"] >= 0.01).mean()*100, 1) if te_n > 0 else 0,
            "te_mfe_above_2pct": round((te["mfe_pct"] >= 0.02).mean()*100, 1) if te_n > 0 else 0,
        })

    summary = pd.DataFrame(records)

    # ── Print summary table ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY TABLE")
    print("=" * 70)
    print(f"{'Thresh':>6} {'n':>5} {'WR':>6} {'PF':>6} {'E':>8} {'MFE%':>7} {'prof%':>6} {'missROI%':>9} {'TEprof%':>8} {'TE MFE>=1%':>11}")
    print("-" * 85)
    for _, r in summary.iterrows():
        print(
            f"{r['threshold']:>6.2f} "
            f"{int(r['total_trades']):>5} "
            f"{r['win_rate_pct']:>6.1f} "
            f"{r['profit_factor']:>6.3f} "
            f"{r['expectancy']:>8.5f} "
            f"{r['mfe_mean_pct']:>7.2f} "
            f"{r['became_profitable_pct']:>6.1f} "
            f"{r['missed_roi_pct']:>9.1f} "
            f"{r['te_ever_profitable_pct']:>8.1f} "
            f"{r['te_mfe_above_1pct']:>11.1f}"
        )

    print(f"\nConclusion: {conclusion}")

    # Save summary
    summary_path = OUTPUT_DIR / f"E001d_summary_{ts}.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Summary: {summary_path}")

    return df, summary, conclusion


if __name__ == "__main__":
    run()
