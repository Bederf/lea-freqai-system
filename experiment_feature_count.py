#!/usr/bin/env python3
"""
Experiment E — Feature Count Selection
=====================================
Compare walk-forward performance across staged feature sets:
  Model A: 3 stable volume features
  Model B: 8 stable features
  Model C: 15 stable features
  Model D: all 28 features (baseline)

Key question: does reducing to a stable core set improve
walk-forward AUC and probability distribution stability?

Usage: python3 experiment_feature_count.py [--pair BTC]
"""

import argparse
import os
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score as AUC, brier_score_loss
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")

# ─── Args ──────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Experiment E: Feature Count Comparison")
parser.add_argument("--pair", default="BTC", choices=["BTC", "ETH"])
parser.add_argument("--output-dir", default="user_data/reports/experiments")
parser.add_argument("--test-days", type=int, default=7)
args = parser.parse_args()

os.makedirs(args.output_dir, exist_ok=True)
DATE = datetime.now().strftime("%Y%m%d_%H%M%S")
PAIR = args.pair
TEST_DAYS = args.test_days

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


# ─── Full feature engineering ────────────────────────────────────
def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    df = df.copy()
    for lag in [1, 3, 6, 12, 24]:
        df[f"%ret_{lag}"] = df["close"].pct_change(lag)
    df["atr14"] = compute_atr(df, 14)
    df["%atr14_rel"] = df["atr14"] / df["close"]
    for win in [3, 5, 10, 20]:
        df[f"vol_ma{win}"] = df["volume"].rolling(win, min_periods=1).mean()
        df[f"vol_ratio_{win}"] = df["volume"] / df[f"vol_ma{win}"].replace(0, 1)
    df["hl_range"] = (df["high"] - df["low"]) / df["close"]
    df["upper_shadow"] = (df["high"] - df[["open", "close"]].max(axis=1)) / df["close"]
    df["lower_shadow"] = (df[["open", "close"]].min(axis=1) - df["low"]) / df["close"]
    df["candle_body"] = (df["close"] - df["open"]) / df["close"]
    df["mom_6"] = df["close"].pct_change(6)
    df["mom_12"] = df["close"].pct_change(12)
    for win in [8, 20, 50]:
        df[f"ema_{win}"] = df["close"].ewm(span=win, min_periods=1).mean()
        df[f"ema_ratio_{win}"] = df["close"] / df[f"ema_{win}"]
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(span=14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).ewm(span=14, min_periods=1).mean()
    df["rsi_14"] = 100 - (100 / (1 + gain / loss.replace(0, 1)))
    df["future_ema_atr"] = df["atr14"].shift(-12)
    df["label"] = (df["future_ema_atr"] > df["atr14"] * 1.05).astype(int)
    feat_cols = [c for c in df.columns
                 if c not in ("ts", "open", "high", "low", "close", "volume",
                               "future_ema_atr", "label")]
    return df.dropna(subset=["label"] + feat_cols), feat_cols


# ─── Walk-forward per feature set ─────────────────────────────────
def walk_forward_sets(
    df: pd.DataFrame,
    feature_sets: dict[str, list[str]],
    train_days: int = 30,
) -> dict[str, list[dict]]:
    """Run walk-forward for each named feature set. Returns {name: [fold_results]}."""
    results = {name: [] for name in feature_sets}

    t_start = df["ts"].iloc[0] + timedelta(days=train_days)
    t_test = t_start + timedelta(days=TEST_DAYS)
    t_end = df["ts"].max()

    while t_test <= t_end:
        train_mask = (df["ts"] >= t_start - timedelta(days=train_days)) & (df["ts"] < t_start)
        test_mask = (df["ts"] >= t_test) & (df["ts"] < t_test + timedelta(days=TEST_DAYS))

        train_df = df[train_mask]
        test_df = df[test_mask]

        if len(train_df) < 200 or len(test_df) < 20:
            t_start += timedelta(days=TEST_DAYS)
            t_test += timedelta(days=TEST_DAYS)
            continue

        y_test = test_df["label"].values
        if len(np.unique(y_test)) < 2:
            t_start += timedelta(days=TEST_DAYS)
            t_test += timedelta(days=TEST_DAYS)
            continue

        for name, feat_cols in feature_sets.items():
            available = [f for f in feat_cols if f in df.columns]
            if len(available) < len(feat_cols):
                print(f"  [WARN] {name}: {len(feat_cols) - len(available)} features missing")

            train_x = train_df[available].values
            y_train = train_df["label"].values
            test_x = test_df[available].values

            if np.any(np.isnan(train_x)) or np.any(np.isnan(test_x)):
                t_start += timedelta(days=TEST_DAYS)
                t_test += timedelta(days=TEST_DAYS)
                continue

            scaler = MinMaxScaler(feature_range=(-1, 1))
            X_train_s = scaler.fit_transform(train_x)
            X_test_s = scaler.transform(test_x)

            c = XGBClassifier(
                objective="binary:logistic", n_estimators=200, max_depth=4,
                learning_rate=0.05, random_state=1, verbosity=0, eval_metric="logloss"
            )
            c.fit(X_train_s, y_train)
            p = c.predict_proba(X_test_s)[:, 1]

            p_clipped = np.clip(p, 1e-6, 1 - 1e-6)
            brier = brier_score_loss(y_test, p_clipped)

            try:
                fold_auc = AUC(y_test, p)
            except ValueError:
                fold_auc = 0.5

            results[name].append({
                "fold_end": str(t_test),
                "train_n": len(train_df),
                "test_n": len(test_df),
                "test_positive_rate": float(y_test.mean()),
                "n_features": len(available),
                "fold_auc": fold_auc,
                "fold_brier": float(brier),
                "prob_mean": float(p.mean()),
                "prob_std": float(p.std()),
                "above_55": float((p >= 0.55).mean()),
                "above_50": float((p >= 0.50).mean()),
            })

        t_start += timedelta(days=TEST_DAYS)
        t_test += timedelta(days=TEST_DAYS)

    return results


# ─── Main ────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("EXPERIMENT E — Feature Count Comparison")
    print("=" * 60)

    print(f"\nLoading {PAIR} candles...")
    df, all_feat_cols = build_features(load_candles(PAIR))
    if df is None:
        print("No data. Exiting.")
        exit(1)

    print(f"  {len(df)} candles, {len(all_feat_cols)} total features")
    print(f"  Positive rate: {df['label'].mean()*100:.1f}%")

    # ── Define staged feature sets ────────────────────────────────
    # Ordered by stability/consistency from Experiment D
    vol_ratio_feats = ["vol_ratio_20", "vol_ratio_10", "vol_ratio_5", "vol_ratio_3"]

    stable_8 = [
        "vol_ratio_20", "vol_ratio_10", "vol_ratio_5", "vol_ratio_3",
        "%ret_1", "candle_body", "hl_range", "lower_shadow",
    ]

    stable_15 = [
        "vol_ratio_20", "vol_ratio_10", "vol_ratio_5", "vol_ratio_3",
        "vol_ma20", "vol_ma10",
        "%ret_1", "%ret_3", "candle_body", "hl_range",
        "lower_shadow", "upper_shadow", "mom_6", "atr14", "%atr14_rel",
    ]

    feature_sets = {
        "A (3 vol)":   vol_ratio_feats,
        "B (8 stable)": stable_8,
        "C (15 stable)": stable_15,
        "D (28 all)":   all_feat_cols,
    }

    print(f"\nFeature sets:")
    for name, feats in feature_sets.items():
        print(f"  {name}: {len(feats)} features")

    # ── Run walk-forward ─────────────────────────────────────────
    print(f"\nRunning walk-forward ({TEST_DAYS}-day test, 30-day train)...")
    results = walk_forward_sets(df, feature_sets, train_days=30)

    all_rows = []
    for name, folds in results.items():
        for f in folds:
            all_rows.append({"model": name, **f})
    rows = pd.DataFrame(all_rows)
    rows.to_csv(f"{args.output_dir}/expE_{PAIR}_{DATE}.csv", index=False)

    # ── Summary table ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("WALK-FORWARD RESULTS BY FEATURE SET")
    print("=" * 70)

    summary_cols = ["model", "n_features", "fold_auc", "fold_brier",
                    "prob_mean", "prob_std", "above_55"]
    summary = rows.groupby("model").agg(
        n_features=("n_features", "first"),
        folds=("fold_auc", "count"),
        AUC_mean=("fold_auc", "mean"),
        AUC_std=("fold_auc", "std"),
        Brier_mean=("fold_brier", "mean"),
        Prob_mean=("prob_mean", "mean"),
        Prob_std=("prob_std", "mean"),
        Pct_above55=("above_55", "mean"),
    ).round(4)
    summary = summary.sort_values("AUC_mean", ascending=False)
    summary = summary.reset_index()

    print(f"\n{'Model':<16} {'N':>3} {'Folds':>6} {'AUC-mean':>9} {'AUC-std':>9} "
          f"{'Brier':>8} {'Prob-mean':>10} {'Prob-std':>9} {'%>55':>7}")
    print("-" * 85)
    for _, r in summary.iterrows():
        print(f"  {r['model']:<14} {r['n_features']:>3} {r['folds']:>6} "
              f"{r['AUC_mean']:>9.4f} {r['AUC_std']:>9.4f} "
              f"{r['Brier_mean']:>8.4f} {r['Prob_mean']:>10.4f} "
              f"{r['Prob_std']:>9.4f} {r['Pct_above55']*100:>6.1f}%")

    # ── Per-fold AUC comparison ───────────────────────────────────
    print("\n\nPER-FOLD AUC COMPARISON")
    print("-" * 85)
    pivot = rows.pivot_table(index="fold_end", columns="model", values="fold_auc")
    pivot = pivot[[m for m in ["A (3 vol)", "B (8 stable)", "C (15 stable)", "D (28 all)"] if m in pivot.columns]]
    # Ensure all columns are float
    for col in pivot.columns:
        pivot[col] = pd.to_numeric(pivot[col], errors="coerce")
    # Best model per fold
    pivot["best"] = pivot.idxmax(axis=1)
    pivot["best_auc"] = pivot[[c for c in pivot.columns if c != "best"]].max(axis=1)
    print(f"  {'Fold end':<12} {'A(3)':>8} {'B(8)':>8} {'C(15)':>8} {'D(28)':>8} {'Best':>12} {'AUC':>8}")
    print("  " + "-" * 70)
    for fold_end, row in pivot.iterrows():
        best_auc_val = row["best_auc"]
        a = f"{row['A (3 vol)']:.4f}" if pd.notna(row.get('A (3 vol)')) else "   n/a "
        b = f"{row['B (8 stable)']:.4f}" if pd.notna(row.get('B (8 stable)')) else "   n/a "
        c = f"{row['C (15 stable)']:.4f}" if pd.notna(row.get('C (15 stable)')) else "   n/a "
        d = f"{row['D (28 all)']:.4f}" if pd.notna(row.get('D (28 all)')) else "   n/a "
        print(f"  {str(fold_end)[:10]:<12} {a:>8} {b:>8} {c:>8} {d:>8} {row['best']:>12} {best_auc_val:>8.4f}")

    # Wins per model
    win_counts = pivot["best"].value_counts()
    print(f"\n  Fold wins:")
    for m in ["A (3 vol)", "B (8 stable)", "C (15 stable)", "D (28 all)"]:
        if m in win_counts.index:
            print(f"    {m}: {win_counts[m]} folds")

    # ── Probability distribution comparison ─────────────────────────
    print("\n\nPREDICTION DISTRIBUTION SUMMARY")
    print("-" * 70)
    for model in ["A (3 vol)", "B (8 stable)", "C (15 stable)", "D (28 all)"]:
        mrows = rows[rows["model"] == model]
        print(f"  {model}:")
        print(f"    Mean probability:  {mrows['prob_mean'].mean():.4f}")
        print(f"    Std probability:   {mrows['prob_std'].mean():.4f}")
        print(f"    % predictions >55: {mrows['above_55'].mean()*100:.1f}%")

    # ── Verdict ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    best_model = summary.iloc[0]["model"]
    best_auc = summary.iloc[0]["AUC_mean"]
    baseline_auc = summary[summary["model"] == "D (28 all)"]["AUC_mean"].values[0]
    improvement = best_auc - baseline_auc

    print(f"\n  Best model:     {best_model}")
    print(f"  Best AUC:      {best_auc:.4f}")
    print(f"  Baseline AUC:  {baseline_auc:.4f} (28-feature model)")
    print(f"  Improvement:   {improvement:+.4f}")

    if improvement > 0.005:
        verdict = (f"✅ REDUCED FEATURES WIN — {best_model} outperforms "
                   f"the 28-feature baseline by {improvement:.4f} AUC")
    elif improvement > -0.005:
        verdict = (f"✅ EQUIVALENT — {best_model} performs comparably to the "
                   f"28-feature baseline ({improvement:+.4f}). Fewer features = less overfitting risk.")
    else:
        verdict = (f"❌ FULL FEATURES WIN — 28-feature baseline outperforms "
                   f"{best_model} by {-improvement:.4f} AUC. Feature reduction not justified.")

    print(f"\n  {verdict}")
    print(f"\n  Interpretation:")
    if best_model == "A (3 vol)":
        print("    The 3 volume-ratio features carry nearly all the predictive signal.")
        print("    A 3-feature model is dramatically simpler and more robust.")
    elif best_model == "B (8 stable)":
        print("    8 stable features capture the full signal with minimal noise.")
        print("    Good balance of simplicity and predictive power.")
    elif best_model == "C (15 stable)":
        print("    15 features is the sweet spot — enough to capture regime interactions")
        print("    without the noise present in the full 28-feature set.")
    else:
        print("    All 28 features appear necessary — no redundancy detected.")
        print("    Regime interactions require the full feature set.")

    print(f"\nSaved: {args.output_dir}/expE_{PAIR}_{DATE}.csv")
