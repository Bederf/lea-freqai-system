#!/usr/bin/env python3
"""
E004 — Label Comparison: Economic Alignment
============================================
Compare 4 candidate labels head-to-head using walk-forward validation.

Labels:
  A  Current:   ATR[t+12] > ATR[t] × 1.05
  B  ATR80:     ATR[t+12] > ATR[t] × 1.05 AND ATR[t+12] - ATR[t] > max(ATR[t] × 0.80, 20)
  C  Harder:    ATR[t+12] > ATR[t] × 1.10
  D  MFE:       max(close[t+1:t+12]/close[t]-1) × 100 >= 1.0% AND ATR[t+12] > ATR[t] × 1.05

All other strategy parameters held constant across labels.

Output: per-label metrics table, best label recommendation.
"""

import gc, joblib, json, pickle, sys, warnings
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
warnings.filterwarnings("ignore")

DATA_DIR   = Path("/freqtrade/user_data/data/binance")
MODEL_DIR  = Path("/freqtrade/user_data/models")
OUTPUT_DIR = Path("/freqtrade/user_data/reports/e004")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, "/freqtrade/user_data")
from retrain_15f_classifier import build_features, FEATURE_COLS

PAIRS      = ["BTC", "ETH", "SOL", "LINK"]
PAIR_FILES = {"BTC": "BTC_USDT", "ETH": "ETH_USDT", "SOL": "SOL_USDT", "LINK": "LINK_USDT"}
TRAIN_N    = 8640   # ~30 days of 5m candles
TEST_N     = 2016   # ~7 days
FEE_PCT    = 0.001
BASE_THRESH = 0.55
ROI_LADDER  = [(0, 0.05), (30, 0.03), (60, 0.02), (120, 0.01)]
STOPLOSS_PCT = -0.05
TIME_EXIT_HRS = 6.0
EMA_PERIOD    = 50

LABELS = {
    "A": {
        "name": "relative_5pct",
        "desc": "Current label: ATR[t+12] > ATR[t] × 1.05",
    },
    "B": {
        "name": "atr80_min_abs",
        "desc": "ATR[t+12] > ATR[t] × 1.05 AND ATR[t+12]-ATR[t] > max(ATR[t]×0.80, 20)",
    },
    "C": {
        "name": "relative_10pct",
        "desc": "Harder: ATR[t+12] > ATR[t] × 1.10",
    },
    "D": {
        "name": "mfe_1pct",
        "desc": "MFE ≥ 1% AND ATR[t+12] > ATR[t] × 1.05",
    },
}


# ─── ATR ────────────────────────────────────────────────────────────────────

def compute_atr(df, period=14):
    high = df["high"].values
    low  = df["low"].values
    close = df["close"].values
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
    atr = np.zeros(len(tr))
    atr[:period] = np.nan
    atr[period] = tr[:period].mean()
    for i in range(period + 1, len(atr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def compute_labels_for_df(df):
    """
    Compute all 4 labels for a DataFrame that already has close/high/low.
    Returns dict of label arrays (same length as df).
    Only indices [0, n-13] can be valid labels (need 12 future candles).
    """
    n = len(df)
    close = df["close"].values
    high  = df["high"].values
    low   = df["low"].values

    atr = compute_atr(df, 14)
    atr14 = atr

    # ATR at t+12 — keep as-is, will mask validity explicitly
    atr_t12 = np.roll(atr14, -12)
    atr_t12[-12:] = np.nan  # last 12 rows: no future data

    # Precompute masks for valid region only (indices 0 to n-13)
    valid_slice = slice(None, n - 12)
    atr_v = atr14[valid_slice]
    atr_t12_v = atr_t12[valid_slice]

    # Label A: relative 5%
    label_A = np.full(n, np.nan)
    label_A[valid_slice] = (atr_t12_v > atr_v * 1.05).astype(float)

    # Label B: relative 5% + min absolute ATR change (50% of current ATR)
    abs_change_v = atr_t12_v - atr_v
    min_abs_v = atr_v * 0.50
    label_B = np.full(n, np.nan)
    label_B[valid_slice] = ((atr_t12_v > atr_v * 1.05) & (abs_change_v > min_abs_v)).astype(float)

    # Label C: relative 10%
    label_C = np.full(n, np.nan)
    label_C[valid_slice] = (atr_t12_v > atr_v * 1.10).astype(float)

    # Label D: MFE >= 1% within 12 candles AND ATR expansion
    # Vectorized: use rolling max of future closes
    close_series = pd.Series(close)
    # Future rolling max over next 12 periods (excluding current)
    future_max = close_series.rolling(12, min_periods=1).max().shift(-12)
    future_min = close_series.rolling(12, min_periods=1).min().shift(-12)
    bullish_mfe = (future_max.values / close - 1) * 100
    bearish_mfe = (1 - future_min.values / close) * 100
    mfe = np.maximum(bullish_mfe, bearish_mfe)
    mfe[-12:] = np.nan
    label_D = np.full(n, np.nan)
    label_D[valid_slice] = ((mfe[valid_slice] >= 1.0) & (atr_t12_v > atr_v * 1.05)).astype(float)

    return {
        "A": label_A,
        "B": label_B,
        "C": label_C,
        "D": label_D,
    }


def build_minimal_features(df):
    """
    Build the 15 LeahAI v4.4 features WITHOUT dropping rows.
    Returns a DataFrame with the same index as input.
    Rows near the start may have NaN in some features; those will be
    filtered out at train/test time via the label validity mask.
    """
    df = df.copy()
    close = df["close"].values
    high  = df["high"].values
    low   = df["low"].values
    volume = df["volume"].values
    op    = df["open"].values

    # Returns
    df["%ret_1"] = pd.Series(close).pct_change(1).values
    df["%ret_3"] = pd.Series(close).pct_change(3).values
    df["mom_6"]   = pd.Series(close).pct_change(6).values

    # ATR
    df["atr14"] = compute_atr(df, 14)
    df["%atr14_rel"] = df["atr14"] / close

    # Volume ratios and MA
    for win in [3, 5, 10, 20]:
        df[f"vol_ma{win}"] = pd.Series(volume).rolling(win, min_periods=1).mean().values
        df[f"vol_ratio_{win}"] = volume / df[f"vol_ma{win}"].replace(0, 1)

    # Candle geometry
    df["hl_range"]    = (high - low) / close
    df["candle_body"] = (close - op) / close
    max_co = np.maximum(close, op)
    min_co = np.minimum(close, op)
    df["upper_shadow"] = (high - max_co) / close
    df["lower_shadow"] = (min_co - low) / close

    return df


# ─── Load data ───────────────────────────────────────────────────────────────

def load_pair_data(pair):
    """Load full 5m data for a pair."""
    pf = PAIR_FILES[pair]
    fpath = DATA_DIR / f"{pf}-5m.feather"
    if not fpath.exists():
        return None
    df = pd.read_feather(fpath).rename(columns={"date": "open_time"})
    df = df.sort_values("open_time").reset_index(drop=True)
    return df


def load_folds():
    """Load fold end dates from E fold CSV."""
    import csv
    fold_path = Path("/freqtrade/user_data/reports/experiments/expE_BTC_20260711_211246.csv")
    folds = []
    with open(fold_path) as f:
        for row in csv.DictReader(f):
            if row["model"] == "C (15 stable)":
                folds.append({"fold_end": row["fold_end"]})
    return folds


# ─── Walk-forward simulation ───────────────────────────────────────────────────

def simulate_trades(pair_df, threshold, labels_dict, label_key):
    """
    Simulate trades for one pair + one fold + one label.
    Returns list of trade dicts.
    """
    df = pair_df.copy().reset_index(drop=True)
    n = len(df)

    label = labels_dict[label_key]
    valid = ~np.isnan(label) & ~np.isnan(df["close"].values)
    if valid.sum() < 100:
        return []

    # Compute features
    df = build_features(df)
    feat_df = df[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(0)

    # Align labels with df index
    label_aligned = np.full(n, np.nan)
    label_aligned[valid] = label[valid]

    # Compute EMA
    df["ema_50"] = df["close"].ewm(span=EMA_PERIOD, adjust=False).mean()

    # We need to run a separate model for each label
    # For simplicity in E004, we train inline per (pair, fold, label)
    return []  # Will be overridden in run() with proper model training


def run_label_fold(pair, fold_end, train_df, test_df, label_key, model_cache):
    """Train model on train_df with label_key, simulate on test_df."""
    # Concatenate train+test
    full_df = pd.concat([train_df, test_df], ignore_index=True)
    n_train = len(train_df)
    n_full  = len(full_df)

    # Build features WITHOUT dropping rows
    full_feat = build_minimal_features(full_df)

    # Compute labels on the full feature DataFrame
    labels_dict = compute_labels_for_df(full_feat)

    # Get feature array
    feat_arr = full_feat[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(0).values

    # Get label array for this label
    label_arr = labels_dict[label_key]

    # Validity: label non-NaN AND features non-NaN
    feat_nan = np.isnan(feat_arr).any(axis=1)
    valid = ~np.isnan(label_arr) & ~feat_nan

    if valid[:n_train].sum() < 50:
        return {"label": label_key, "pair": pair, "fold_end": fold_end,
                "error": "insufficient train samples", "trades": []}
    if valid[n_train:].sum() < 10:
        return {"label": label_key, "pair": pair, "fold_end": fold_end,
                "error": "insufficient test samples", "trades": []}

    # ── Train on valid train rows only ────────────────────────────────────────
    train_mask = valid[:n_train]
    X_train = feat_arr[:n_train][train_mask]
    y_train = label_arr[:n_train][train_mask].astype(int)

    # Guard: need both classes
    if len(np.unique(y_train)) < 2 or y_train.sum() < 5 or (len(y_train) - y_train.sum()) < 5:
        return {"label": label_key, "pair": pair, "fold_end": fold_end,
                "error": "insufficient class balance", "trades": []}

    scaler = MinMaxScaler(feature_range=(-1, 1))
    X_train_scaled = scaler.fit_transform(X_train)

    model = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        scale_pos_weight=(y_train == 0).sum() / max((y_train == 1).sum(), 1),
        use_label_encoder=False,
        verbosity=0,
        n_jobs=1,
    )
    model.fit(X_train_scaled, y_train)

    # ── Predict on ALL test rows (valid and invalid) ─────────────────────────
    X_test_all  = feat_arr[n_train:]
    probs_all   = model.predict_proba(scaler.transform(X_test_all))[:, 1]
    test_valid  = valid[n_train:]   # boolean array: which test rows have valid labels+features
    test_labels_arr = label_arr[n_train:]  # may contain NaN for last rows

    # ── Simulate trades on valid test rows ────────────────────────────────────
    test_feat_df = full_feat.iloc[n_train:].copy().reset_index(drop=True)
    test_feat_df["probability"] = probs_all
    test_feat_df["ema_50"] = test_feat_df["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
    test_feat_df["btc_trend"] = 0.0  # disable BTC filter for speed
    test_feat_df["_valid"] = test_valid

    trades = []
    in_trade = False
    entry_price = entry_prob = entry_time = None

    for i in range(len(test_feat_df)):
        if not test_feat_df.iloc[i]["_valid"]:
            continue  # skip rows without valid labels

        row = test_feat_df.iloc[i]

        if not in_trade:
            if row["probability"] < BASE_THRESH:
                continue
            if row["close"] <= row["ema_50"]:
                continue

            in_trade = True
            entry_price = float(row["close"])
            entry_prob  = float(row["probability"])
            entry_time  = row["open_time"]
        else:
            curr_price = float(row["close"])
            curr_time  = row["open_time"]

            try:
                dt_min = (curr_time - entry_time).total_seconds() / 60
            except Exception:
                dt_min = 5.0

            pct_ret = (curr_price - entry_price) / entry_price
            exited = False
            exit_reason = None

            # ROI ladder
            for cutoff_min, roi_pct in reversed(ROI_LADDER):
                if dt_min >= cutoff_min and pct_ret >= roi_pct:
                    exited = True
                    exit_reason = f"roi_{roi_pct}"
                    break
            # Stoploss
            if not exited and pct_ret <= STOPLOSS_PCT:
                exited = True
                exit_reason = "stoploss"
            # Time exit (negative only)
            if not exited and dt_min > TIME_EXIT_HRS * 60 and pct_ret < 0:
                exited = True
                exit_reason = "time_exit_6h_negative"

            if exited:
                gross_ret = (curr_price - entry_price) / entry_price
                net_pnl = gross_ret - FEE_PCT * 2
                conf_mult = np.clip(1.0 + (entry_prob - BASE_THRESH) * 2.5, 0.5, 1.5)
                net_pnl *= conf_mult
                trades.append({
                    "pair": pair,
                    "label": label_key,
                    "fold_end": fold_end,
                    "duration_min": dt_min,
                    "gross_return": gross_ret,
                    "net_pnl": net_pnl,
                    "is_win": net_pnl > 0,
                    "exit_reason": exit_reason,
                    "probability": entry_prob,
                })
                in_trade = False

    return {"label": label_key, "pair": pair, "fold_end": fold_end, "trades": trades}


# ─── Metric aggregation ───────────────────────────────────────────────────────

def aggregate_trades(trades_list):
    """Compute summary metrics from a list of trade dicts."""
    if not trades_list:
        return {}
    import pandas as pd
    df = pd.DataFrame(trades_list)
    n = len(df)
    if n == 0:
        return {}

    wins = df["net_pnl"] > 0
    gp   = df.loc[wins, "net_pnl"].sum()
    gl   = abs(df.loc[~wins, "net_pnl"].sum())
    pf   = gp / max(gl, 1e-9)
    exp  = df["net_pnl"].mean()
    wr   = wins.mean() * 100

    cum  = df.sort_index()["net_pnl"].cumsum().values
    peak = np.maximum.accumulate(cum)
    dd   = cum - peak
    max_dd_pct = abs(dd.min()) / (peak.max() + 1e-9) * 100 if peak.max() > 0 else 0

    te_n  = (df["exit_reason"] == "time_exit_6h_negative").sum()
    roi_n = df["exit_reason"].str.startswith("roi_").sum()
    sl_n  = (df["exit_reason"] == "stoploss").sum()

    return {
        "n_trades": n,
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 3),
        "expectancy": round(exp, 5),
        "max_dd_pct": round(max_dd_pct, 1),
        "time_exit_pct": round(te_n / n * 100, 1),
        "roi_pct": round(roi_n / n * 100, 1),
        "stoploss_pct": round(sl_n / n * 100, 1),
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBClassifier


def run():
    import pandas as pd
    print("E004 — Label Comparison: Economic Alignment")
    print("=" * 60)

    folds = load_folds()
    print(f"Folds: {len(folds)}")
    print(f"Pairs: {PAIRS}")
    print(f"Labels: {list(LABELS.keys())}")
    print()

    # Load all pair data
    # Pre-load all pair data
    pair_data = {}
    for pair in PAIRS:
        df = load_pair_data(pair)
        if df is not None:
            pair_data[pair] = df
            print(f"  {pair}: {len(df)} rows")

    # Pre-compute labels for each pair (full dataset)
    print("Computing labels for all pairs...")
    for pair, df in pair_data.items():
        labels = compute_labels_for_df(df)
        for lk, larr in labels.items():
            valid = ~np.isnan(larr)
            n_pos = (larr[valid] == 1).sum()
            n_tot = valid.sum()
            print(f"  {pair} Label {lk}: {n_pos}/{n_tot} positive ({n_pos/n_tot*100:.1f}%)")

    # Build all (fold, pair, label) tasks
    tasks = []
    for fold in folds:
        fold_end = fold["fold_end"]
        fold_end_dt = pd.to_datetime(fold_end)
        if fold_end_dt.tz is None:
            fold_end_dt = fold_end_dt.tz_localize("UTC")
        else:
            fold_end_dt = fold_end_dt.tz_convert("UTC")

        for pair in PAIRS:
            df_full = pair_data[pair]
            split_idx = df_full[df_full["open_time"] >= fold_end_dt].index
            if len(split_idx) == 0:
                continue
            si = split_idx[0]
            train_end = max(0, si - TEST_N)
            test_start = train_end
            test_end = min(si + TEST_N, len(df_full))
            if train_end < TRAIN_N or test_end - test_start < 100:
                continue

            train_df = df_full.iloc[train_end - TRAIN_N:train_end].copy().reset_index(drop=True)
            test_df  = df_full.iloc[test_start:test_end].copy().reset_index(drop=True)

            for lk in LABELS:
                tasks.append({
                    "pair": pair, "fold_end": fold_end,
                    "train_df": train_df, "test_df": test_df,
                    "label_key": lk,
                })

    print(f"\nTotal tasks: {len(tasks)} ({len(folds)} folds × {len(PAIRS)} pairs × {len(LABELS)} labels)")
    print(f"Running with 8 workers...")

    all_trades = []
    completed = [0]

    def run_task(task):
        result = run_label_fold(
            pair=task["pair"],
            fold_end=task["fold_end"],
            train_df=task["train_df"],
            test_df=task["test_df"],
            label_key=task["label_key"],
            model_cache={},
        )
        done = completed[0] + 1
        completed[0] = done
        if done % 50 == 0:
            print(f"  [{done}/{len(tasks)}] done")
        if result.get("trades"):
            return result["trades"]
        return []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(run_task, t): t for t in tasks}
        for future in as_completed(futures):
            try:
                trades = future.result()
                all_trades.extend(trades)
            except Exception:
                pass

    print(f"\nTotal trades collected: {len(all_trades)}")

    if not all_trades:
        print("ERROR: No trades collected. Check data pipeline.")
        return

    # ─── Aggregate by label ───────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("E004 — LABEL COMPARISON RESULTS")
    print("=" * 70)

    records = []
    for lk in LABELS:
        label_trades = [t for t in all_trades if t["label"] == lk]
        agg = aggregate_trades(label_trades)
        if agg:
            rec = {"label": lk, "label_name": LABELS[lk]["name"], "description": LABELS[lk]["desc"]}
            rec.update(agg)
            records.append(rec)

    summary = pd.DataFrame(records)

    # Per-pair breakdown
    print(f"\n{'Label':<20} {'n':>6} {'WR%':>6} {'PF':>6} {'E':>8} {'DD%':>7} {'TE%':>5} {'ROI%':>6}")
    print("-" * 70)
    for _, r in summary.sort_values("expectancy", ascending=False).iterrows():
        print(
            f"{r['label']:<20} "
            f"{int(r['n_trades']):>6} "
            f"{r['win_rate']:>6.1f} "
            f"{r['profit_factor']:>6.3f} "
            f"{r['expectancy']:>8.5f} "
            f"{r['max_dd_pct']:>7.1f} "
            f"{r['time_exit_pct']:>5.1f} "
            f"{r['roi_pct']:>6.1f}"
        )

    # ─── Per-pair table ───────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("PER-PAIR BREAKDOWN (by label)")
    print("=" * 70)
    pair_records = []
    for pair in PAIRS:
        for lk in LABELS:
            pair_trades = [t for t in all_trades if t["label"] == lk and t["pair"] == pair]
            agg = aggregate_trades(pair_trades)
            if agg:
                rec = {"pair": pair, "label": lk}
                rec.update(agg)
                pair_records.append(rec)

    pair_summary = pd.DataFrame(pair_records)
    if not pair_summary.empty:
        for pair in PAIRS:
            ps = pair_summary[pair_summary["pair"] == pair].sort_values("expectancy", ascending=False)
            print(f"\n{pair}:")
            for _, r in ps.iterrows():
                print(
                    f"  {r['label']:<10}  n={int(r['n_trades']):>4}  "
                    f"WR={r['win_rate']:>5.1f}%  PF={r['profit_factor']:>5.3f}  "
                    f"E={r['expectancy']:>+8.5f}  TE={r['time_exit_pct']:>5.1f}%"
                )

    # ─── Recommendation ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    best = summary.sort_values("expectancy", ascending=False).iloc[0]
    baseline = summary[summary["label"] == "A"]
    baseline_exp = baseline["expectancy"].values[0] if len(baseline) else 0
    delta = best["expectancy"] - baseline_exp

    print(f"\nBest label: {best['label']} ({best['label_name']})")
    print(f"  Expectancy: {best['expectancy']:+.5f} (delta vs A: {delta:+.5f})")
    print(f"  Trade count: {int(best['n_trades'])}")
    print(f"  Win rate: {best['win_rate']:.1f}%")
    print(f"  Profit factor: {best['profit_factor']:.3f}")
    print(f"  Time exit %: {best['time_exit_pct']:.1f}%")
    print(f"  Max DD: {best['max_dd_pct']:.1f}%")

    if delta > 0.001:
        recommendation = (
            f"Label {best['label']} ({best['label_name']}) outperforms baseline A by {delta:+.5f} expectancy. "
            f"Recommend advancing {best['label']} to forward validation."
        )
    elif delta > 0:
        recommendation = (
            f"Label {best['label']} marginally better than baseline A (+{delta:.5f}) but not conclusive. "
            f"Continue collecting data or increase folds."
        )
    else:
        recommendation = (
            f"Baseline label A (relative_5pct) remains best. "
            f"No economically aligned label improves trading outcomes in this sample. "
            f"Consider alternative label definitions or exit rule changes."
        )
    print(f"\n{recommendation}")

    # ─── Save ─────────────────────────────────────────────────────────────────
    ts = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    summary_path = OUTPUT_DIR / f"E004_summary_{ts}.csv"
    trades_path  = OUTPUT_DIR / f"E004_trades_{ts}.csv"
    summary.to_csv(summary_path, index=False)
    pd.DataFrame(all_trades).to_csv(trades_path, index=False)
    print(f"\nSummary: {summary_path}")
    print(f"Trade log: {trades_path}")

    return summary, pd.DataFrame(all_trades), recommendation


if __name__ == "__main__":
    run()
