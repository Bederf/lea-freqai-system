#!/usr/bin/env python3
"""
Experiment D — Feature Stability
================================
Walk-forward evaluation measuring how feature predictive rankings change
across folds. Unstable rankings = model chasing transient relationships.

Key question: do the same features drive predictions across all market
regimes, or does the model latch onto different signals in different periods?

Usage: python3 experiment_feature_stability.py [--pair BTC]
"""

import argparse
import os
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.metrics import roc_auc_score as AUC
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")

# ─── Args ──────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Experiment D: Feature Stability")
parser.add_argument("--pair", default="BTC", choices=["BTC", "ETH"])
parser.add_argument("--output-dir", default="user_data/reports/experiments")
parser.add_argument("--test-days", type=int, default=7)
parser.add_argument("--top-n", type=int, default=15)
args = parser.parse_args()

os.makedirs(args.output_dir, exist_ok=True)
DATE = datetime.now().strftime("%Y%m%d_%H%M%S")
PAIR = args.pair
TEST_DAYS = args.test_days
TOP_N = args.top_n


# ─── Candle loader ───────────────────────────────────────────────
def load_candles(pair: str, tf: str = "5m") -> pd.DataFrame | None:
    pf = pair.replace("/", "_")
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
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return pd.Series(atr, index=df.index)


# ─── Feature engineering (all features, labeled) ─────────────────
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Returns
    for lag in [1, 3, 6, 12, 24]:
        df[f"%ret_{lag}"] = df["close"].pct_change(lag)
    # ATR
    df["atr14"] = compute_atr(df, 14)
    df["%atr14_rel"] = df["atr14"] / df["close"]
    # Volume
    for win in [3, 5, 10, 20]:
        df[f"vol_ma{win}"] = df["volume"].rolling(win, min_periods=1).mean()
        df[f"vol_ratio_{win}"] = df["volume"] / df[f"vol_ma{win}"].replace(0, 1)
    # High-low ratio
    df["hl_range"] = (df["high"] - df["low"]) / df["close"]
    df["upper_shadow"] = (df["high"] - df[["open", "close"]].max(axis=1)) / df["close"]
    df["lower_shadow"] = (df[["open", "close"]].min(axis=1) - df["low"]) / df["close"]
    # Candle direction
    df["candle_body"] = (df["close"] - df["open"]) / df["close"]
    # Momentum
    df["mom_6"] = df["close"].pct_change(6)
    df["mom_12"] = df["close"].pct_change(12)
    # EMA features
    for win in [8, 20, 50]:
        df[f"ema_{win}"] = df["close"].ewm(span=win, min_periods=1).mean()
        df[f"ema_ratio_{win}"] = df["close"] / df[f"ema_{win}"]
    # RSI-like
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(span=14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).ewm(span=14, min_periods=1).mean()
    df["rsi_14"] = 100 - (100 / (1 + gain / loss.replace(0, 1)))
    # Label: vol expansion 12 candles ahead
    df["future_ema_atr"] = df["atr14"].shift(-12)
    df["label"] = (df["future_ema_atr"] > df["atr14"] * 1.05).astype(int)

    feat_cols = [c for c in df.columns if c not in ("ts", "open", "high", "low", "close", "volume", "future_ema_atr", "label")]
    return df.dropna(subset=["label"] + feat_cols), feat_cols


# ─── Per-feature AUC in a fold ──────────────────────────────────
def fold_feature_aucs(test_df: pd.DataFrame, feat_cols: list[str]) -> dict:
    """Return {feature: auc} for all features where label has both classes."""
    y = test_df["label"].values
    if len(np.unique(y)) < 2:
        return {}
    aucs = {}
    for f in feat_cols:
        vals = test_df[f].values
        if np.std(vals) < 1e-8:
            continue
        try:
            aucs[f] = AUC(y, vals)
        except Exception:
            pass
    return aucs


# ─── Main ────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("EXPERIMENT D — Feature Stability")
    print("=" * 60)

    print(f"\nLoading {PAIR} candles...")
    df = load_candles(PAIR)
    if df is None:
        print("No data. Exiting.")
        exit(1)

    df, feat_cols = build_features(df)
    n_feats = len(feat_cols)
    print(f"  {len(df)} candles, {n_feats} features")
    print(f"  Positive rate: {df['label'].mean()*100:.1f}%")
    print(f"  Top-N tracking: {TOP_N}")

    # Walk forward through data with 30-day training / 7-day test
    train_days = 30
    t_start = df["ts"].iloc[0] + timedelta(days=train_days)
    t_test = t_start + timedelta(days=TEST_DAYS)
    t_end = df["ts"].max()

    fold_feature_aucs_all = []  # list of dicts, one per fold
    fold_times = []

    while t_test <= t_end:
        train_mask = (df["ts"] >= t_start - timedelta(days=train_days)) & (df["ts"] < t_start)
        test_mask = (df["ts"] >= t_test) & (df["ts"] < t_test + timedelta(days=TEST_DAYS))

        train_df = df[train_mask].dropna(subset=feat_cols)
        test_df = df[test_mask].dropna(subset=feat_cols)

        if len(train_df) < 200 or len(test_df) < 20:
            t_start += timedelta(days=TEST_DAYS)
            t_test += timedelta(days=TEST_DAYS)
            continue

        y_test = test_df["label"].values
        if len(np.unique(y_test)) < 2:
            t_start += timedelta(days=TEST_DAYS)
            t_test += timedelta(days=TEST_DAYS)
            continue

        # Train XGBoost classifier on this fold's data
        X_train = train_df[feat_cols].values
        y_train = train_df["label"].values
        X_test = test_df[feat_cols].values

        scaler = MinMaxScaler(feature_range=(-1, 1))
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        c = XGBClassifier(
            objective="binary:logistic", n_estimators=200, max_depth=4,
            learning_rate=0.05, random_state=1, verbosity=0, eval_metric="logloss"
        )
        c.fit(X_train_s, y_train)

        # Per-fold feature AUCs
        aucs = fold_feature_aucs(test_df, feat_cols)

        # XGBoost feature importances
        xgb_importances = dict(zip(feat_cols, c.feature_importances_))

        fold_feature_aucs_all.append(aucs)
        fold_times.append(t_test)

        t_start += timedelta(days=TEST_DAYS)
        t_test += timedelta(days=TEST_DAYS)

    n_folds = len(fold_feature_aucs_all)
    print(f"\n  {n_folds} walk-forward folds analyzed")

    # ── Build per-fold ranking tables ─────────────────────────────────
    # auc_df: features x folds, values = AUC
    auc_df = pd.DataFrame(fold_feature_aucs_all, index=fold_times).T
    auc_df["auc_mean"] = auc_df.iloc[:, :n_folds].mean(axis=1)
    auc_df["auc_std"] = auc_df.iloc[:, :n_folds].std(axis=1)

    # rank_df: features x folds, values = rank position (1 = highest AUC in that fold)
    rank_df = auc_df.iloc[:, :n_folds].rank(ascending=False)
    rank_df["rank_mean"] = rank_df.iloc[:, :n_folds].mean(axis=1)
    rank_df["rank_std"] = rank_df.iloc[:, :n_folds].std(axis=1)
    # Consistency = 1 - normalized rank volatility (0..1, higher = more stable)
    max_std = n_folds / 2  # roughly max possible std for a rank distribution
    rank_df["rank_consistency"] = 1 - rank_df["rank_std"] / max_std

    # Merge AUC and rank stats
    stat_df = auc_df[["auc_mean", "auc_std"]].join(rank_df[["rank_mean", "rank_std", "rank_consistency"]])
    stat_df = stat_df.sort_values("auc_mean", ascending=False)

    print("\n" + "=" * 70)
    print("FEATURE RANK STABILITY ANALYSIS")
    print("=" * 70)

    print(f"\nTop {TOP_N} features by mean AUC across folds:")
    print(f"{'Feature':<25} {'AUC-mean':>10} {'AUC-std':>10} {'Rank-mean':>10} {'Rank-std':>10} {'Consist.':>10}")
    print("-" * 70)
    for feat in stat_df.head(TOP_N).index:
        r = stat_df.loc[feat]
        print(f"  {feat:<23} {r['auc_mean']:>10.4f} {r['auc_std']:>10.4f} {r['rank_mean']:>10.1f} {r['rank_std']:>10.2f} {r['rank_consistency']:>10.3f}")

    # ── Top-N per fold ───────────────────────────────────────────────
    # Which features are in top-N for each fold?
    top_n_per_fold = auc_df.iloc[:, :n_folds].apply(
        lambda col: col.nlargest(TOP_N).index.tolist(), axis=0
    )
    fold_top_sets = [set(top_n_per_fold[f]) for f in top_n_per_fold.columns]

    # Intersection: features in top-N for ALL folds
    always_in_top = fold_top_sets[0]
    for s in fold_top_sets[1:]:
        always_in_top &= s

    # Jaccard similarity between consecutive fold top-N sets
    jaccards = []
    for i in range(1, len(fold_top_sets)):
        inter = len(fold_top_sets[i] & fold_top_sets[i-1])
        union = len(fold_top_sets[i] | fold_top_sets[i-1])
        jaccards.append(inter / union if union > 0 else 0)

    print(f"\n\nTop-{TOP_N} FEATURE OVERLAP ACROSS FOLDS")
    print("-" * 70)
    print(f"  Features in top-{TOP_N} for ALL {n_folds} folds: {len(always_in_top)}")
    for f in sorted(always_in_top):
        print(f"    - {f}")
    if not always_in_top:
        print("    (none)")

    print(f"\n  Mean Jaccard similarity (consecutive folds): {np.mean(jaccards):.3f}")
    print(f"  Jaccard range: {min(jaccards):.3f} – {max(jaccards):.3f}")

    # Most volatile features (rank changes the most across folds)
    print(f"\n\nMOST VOLATILE FEATURES (rank varies most across folds):")
    print("-" * 70)
    volatile = stat_df.sort_values("rank_std", ascending=False).head(10)
    for feat in volatile.index:
        r = stat_df.loc[feat]
        print(f"  {feat:<25} rank_std={r['rank_std']:.2f}  auc={r['auc_mean']:.4f}  consistency={r['rank_consistency']:.3f}")

    # Most stable features (above 0.52 AUC)
    print(f"\n\nMOST STABLE FEATURES (rank consistent across folds):")
    print("-" * 70)
    stable = stat_df[stat_df["auc_mean"] > 0.52].sort_values("rank_consistency", ascending=False).head(10)
    for feat in stable.index:
        r = stat_df.loc[feat]
        print(f"  {feat:<25} rank_std={r['rank_std']:.2f}  auc={r['auc_mean']:.4f}  consistency={r['rank_consistency']:.3f}")

    # Save
    out_base = f"{args.output_dir}/expD_{PAIR}_{DATE}"
    auc_df.to_csv(f"{out_base}_aucs.csv")
    stat_df.to_csv(f"{out_base}_stability.csv")

    print(f"\n\nSaved:")
    print(f"  {out_base}_aucs.csv      (per-fold feature AUCs)")
    print(f"  {out_base}_stability.csv (stability metrics)")

    # ── Overall verdict ────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    mean_jacc = np.mean(jaccards) if jaccards else 0
    n_stable = len(always_in_top)

    if mean_jacc > 0.6 and n_stable >= 3:
        verdict = "✅ STABLE — Features retain relative importance across regimes"
    elif mean_jacc > 0.4 or n_stable >= 1:
        verdict = "⚠️  MIXED — Some features stable, others regime-dependent"
    else:
        verdict = "❌ UNSTABLE — Feature importance shifts dramatically with regime"

    print(f"  {verdict}")
    print(f"  Mean Jaccard (top-{TOP_N} overlap): {mean_jacc:.3f}")
    print(f"  Features in top-{TOP_N} every fold: {n_stable}")
    print(f"  Interpretation: ", end="")
    if mean_jacc < 0.3:
        print("Features are largely regime-dependent — model is likely chasing noise.")
    elif mean_jacc < 0.5:
        print("Some stable features exist but many are regime-sensitive — feature reduction risky without filtering.")
    else:
        print("Core feature set is reasonably stable — feature reduction may help generalization.")
