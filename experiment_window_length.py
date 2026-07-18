#!/usr/bin/env python3
"""
Experiment B — Training Window Length
===================================
Walk-forward evaluation across 15/30/60/90-day training windows.
Key question: does longer training produce more stable probability distributions
and better generalization across changing market regimes?

Usage: python3 experiment_window_length.py [--pair BTC] [--max-window 90]
"""

import argparse
import json
import os
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score as AUC, average_precision_score as APS, brier_score_loss
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBClassifier, XGBRegressor

warnings.filterwarnings("ignore")

# ─── Args ──────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Experiment B: Training Window")
parser.add_argument("--pair", default="BTC", choices=["BTC", "ETH", "SOL", "LINK"])
parser.add_argument("--output-dir", default="user_data/reports/experiments")
parser.add_argument("--max-window", type=int, default=90)
parser.add_argument("--test-days", type=int, default=7)
args = parser.parse_args()

os.makedirs(args.output_dir, exist_ok=True)
DATE = datetime.now().strftime("%Y%m%d_%H%M%S")
PAIR = args.pair
TEST_DAYS = args.test_days


# ─── Candle loader ───────────────────────────────────────────────
def load_candles(pair: str, tf: str = "5m") -> pd.DataFrame | None:
    pf = pair.replace("/", "_")
    # Normalize: BTC -> BTC_USDT, ETH -> ETH_USDT
    if not pf.endswith("USDT") and len(pf) <= 6:
        pf = f"{pf}_USDT"
    fpath = Path(f"user_data/data/binance/{pf}-{tf}.feather")
    if not fpath.exists():
        print(f"  [WARN] No candle file: {fpath}")
        return None
    df = pd.read_feather(fpath)
    df = df.rename(columns={"date": "ts"})
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("UTC")
    else:
        df["ts"] = df["ts"].dt.tz_convert("UTC")
    return df.sort_values("ts").reset_index(drop=True)


# ─── ATR ─────────────────────────────────────────────────────────
def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    tr = np.maximum(
        high - low,
        np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1)))
    )
    atr = np.zeros(len(tr))
    atr[:period] = np.nan
    atr[period] = tr[:period].mean()
    for i in range(period + 1, len(atr)):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return pd.Series(atr, index=df.index)


# ─── Feature engineering ────────────────────────────────────────
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["%ret_1"] = df["close"].pct_change(1)
    df["%ret_3"] = df["close"].pct_change(3)
    df["%ret_6"] = df["close"].pct_change(6)
    df["atr14"] = compute_atr(df, 14)
    df["%atr14_rel"] = df["atr14"] / df["close"]
    df["vol_ma5"] = df["volume"].rolling(5, min_periods=1).mean()
    df["vol_ratio"] = df["volume"] / df["vol_ma5"].replace(0, 1)
    # Label: vol expansion 12 candles (60 min) ahead
    df["future_ema_atr"] = df["atr14"].shift(-12)
    df["label"] = (df["future_ema_atr"] > df["atr14"] * 1.05).astype(int)
    feat_cols = ["%ret_1", "%ret_3", "%ret_6", "%atr14_rel", "vol_ratio"]
    return df.dropna(subset=["label"] + feat_cols)


# ─── Walk-forward evaluation ────────────────────────────────────
def walk_forward(df: pd.DataFrame, train_days: int) -> list[dict]:
    """Train on train_days, test on next TEST_DAYS. Walk forward through data."""
    results = []
    feature_cols = ["%ret_1", "%ret_3", "%ret_6", "%atr14_rel", "vol_ratio"]

    t_start = df["ts"].iloc[0] + timedelta(days=train_days)
    t_test = t_start + timedelta(days=TEST_DAYS)
    t_end = df["ts"].max()

    while t_test <= t_end:
        train_mask = (df["ts"] >= t_start - timedelta(days=train_days)) & (df["ts"] < t_start)
        test_mask = (df["ts"] >= t_test) & (df["ts"] < t_test + timedelta(days=TEST_DAYS))

        train_df = df[train_mask].dropna(subset=feature_cols)
        test_df = df[test_mask].dropna(subset=feature_cols)

        if len(train_df) < 100 or len(test_df) < 20:
            t_start += timedelta(days=TEST_DAYS)
            t_test += timedelta(days=TEST_DAYS)
            continue

        X_train = train_df[feature_cols].values
        y_train = train_df["label"].values
        X_test = test_df[feature_cols].values
        y_test = test_df["label"].values

        scaler = MinMaxScaler(feature_range=(-1, 1))
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # Clf
        c = XGBClassifier(objective="binary:logistic", n_estimators=200, max_depth=4,
                         learning_rate=0.05, random_state=1, verbosity=0, eval_metric="logloss")
        c.fit(X_train, y_train)
        p_clf = c.predict_proba(X_test)[:, 1]

        # Reg
        r = XGBRegressor(objective="reg:squarederror", n_estimators=200, max_depth=4,
                          learning_rate=0.05, random_state=1, verbosity=0)
        r.fit(X_train, y_train)
        p_reg = np.clip(r.predict(X_test), 0, 1)

        # LR
        lr_m = LogisticRegression(max_iter=1000, random_state=1)
        lr_m.fit(X_train_s, y_train)
        p_lr = lr_m.predict_proba(X_test_s)[:, 1]

        results.append({
            "window_days": train_days,
            "train_n": len(train_df),
            "test_n": len(test_df),
            "test_positive_rate": float(y_test.mean()),
            "clf_auc": float(AUC(y_test, p_clf)) if len(np.unique(y_test)) > 1 else 0.5,
            "clf_brier": float(brier_score_loss(y_test, p_clf)),
            "clf_prob_mean": float(p_clf.mean()),
            "clf_prob_std": float(p_clf.std()),
            "clf_above_thresh": float((p_clf >= 0.55).mean()),
            "reg_auc": float(AUC(y_test, p_reg)) if len(np.unique(y_test)) > 1 else 0.5,
            "reg_brier": float(brier_score_loss(y_test, p_reg)),
            "reg_prob_mean": float(p_reg.mean()),
            "reg_prob_std": float(p_reg.std()),
            "reg_above_thresh": float((p_reg >= 0.55).mean()),
            "lr_prob_mean": float(p_lr.mean()),
            "lr_prob_std": float(p_lr.std()),
            "lr_above_thresh": float((p_lr >= 0.55).mean()),
        })

        t_start += timedelta(days=TEST_DAYS)
        t_test += timedelta(days=TEST_DAYS)

    return results


# ─── Main ────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("EXPERIMENT B — Training Window Length")
    print("=" * 60)

    print(f"\nLoading {PAIR} candles...")
    df = load_candles(PAIR)
    if df is None:
        print("No data. Exiting."); exit(1)
    df = build_features(df)
    print(f"  {len(df)} candles: {df['ts'].min()} to {df['ts'].max()}")
    print(f"  Positive rate: {df['label'].mean()*100:.1f}%")
    print(f"  Test days per fold: {TEST_DAYS}")

    all_results = []
    for window in [15, 30, 60, args.max_window]:
        print(f"\n  [{window}-day window]...", end=" ", flush=True)
        res = walk_forward(df, window)
        print(f"{len(res)} folds")
        all_results.extend(res)

    rows = pd.DataFrame(all_results)
    out_base = f"{args.output_dir}/expB_{PAIR}_{DATE}"
    rows.to_csv(f"{out_base}.csv", index=False)

    # Summary
    print(f"\n{'='*70}")
    print("WALK-FORWARD SUMMARY")
    print(f"{'='*70}")
    print(f"\n{'Window':>8} {'AUC-Clf':>10} {'AUC-Reg':>10} {'Brier-Clf':>10} {'Prob-Clf':>10} {'%>55':>8}")
    print("-" * 70)
    for w in sorted(rows["window_days"].unique()):
        wr = rows[rows["window_days"] == w]
        clf_auc = wr["clf_auc"].mean()
        reg_auc = wr["reg_auc"].mean()
        clf_brier = wr["clf_brier"].mean()
        clf_prob = wr["clf_prob_mean"].mean()
        clf_thr = wr["clf_above_thresh"].mean()
        print(f"  {w:>6}d {clf_auc:>10.4f} {reg_auc:>10.4f} {clf_brier:>10.4f} {clf_prob:>10.4f} {clf_thr*100:>7.1f}%")

    # Correlation: window vs prob_mean
    means = rows.groupby("window_days")["clf_prob_mean"].mean()
    if len(means) >= 2:
        corr = np.corrcoef(means.index.values, means.values)[0, 1]
        print(f"\n  Window vs prob_mean correlation: {corr:+.3f}")
        if corr > 0.3:
            print("  ✅ Longer window → higher live probabilities (less compression)")
        elif corr < -0.3:
            print("  ⚠️  Longer window → lower live probabilities (more compression)")

    print(f"\nSaved: {out_base}.csv")
