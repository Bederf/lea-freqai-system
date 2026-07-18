#!/usr/bin/env python3
"""
Retrain 15-Feature Classifier (v4.4)
====================================
Train XGBClassifier on full historical data using the 15 validated stable
features from Experiment E. Save with full metadata for deployment.

Features (Experiment E validated):
  - vol_ratio_20, vol_ratio_10, vol_ratio_5, vol_ratio_3
  - vol_ma20, vol_ma10
  - %ret_1, %ret_3, candle_body, hl_range
  - lower_shadow, upper_shadow, mom_6, atr14, %atr14_rel
"""

import json
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBClassifier
import joblib

warnings.filterwarnings("ignore")

OUTPUT_DIR = Path("user_data/models")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Feature list (validated in Experiment E) ──────────────────────
FEATURE_COLS = [
    "vol_ratio_20", "vol_ratio_10", "vol_ratio_5", "vol_ratio_3",
    "vol_ma20", "vol_ma10",
    "%ret_1", "%ret_3", "candle_body", "hl_range",
    "lower_shadow", "upper_shadow", "mom_6", "atr14", "%atr14_rel",
]

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


# ─── Feature engineering ─────────────────────────────────────────
def build_features(df: pd.DataFrame) -> pd.DataFrame:
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
    df["future_ema_atr"] = df["atr14"].shift(-12)
    df["label"] = (df["future_ema_atr"] > df["atr14"] * 1.05).astype(int)
    return df.dropna(subset=["label"] + FEATURE_COLS)


# ─── Load and train ─────────────────────────────────────────────
def load_candles(pair: str) -> pd.DataFrame | None:
    pf = pair.replace("/", "_")
    if not pf.endswith("USDT") and len(pf) <= 6:
        pf = f"{pf}_USDT"
    fpath = Path(f"user_data/data/binance/{pf}-5m.feather")
    if not fpath.exists():
        print(f"  [WARN] No file: {fpath}")
        return None
    df = pd.read_feather(fpath).rename(columns={"date": "ts"})
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("UTC")
    else:
        df["ts"] = df["ts"].dt.tz_convert("UTC")
    return df.sort_values("ts").reset_index(drop=True)


if __name__ == "__main__":
    pairs = ["BTC", "ETH", "SOL", "LINK"]

    for pair in pairs:
        print(f"\n{'='*60}")
        print(f"Retraining {pair} — 15-feature classifier v4.4")
        print("=" * 60)

        df = load_candles(pair)
        if df is None:
            print(f"  Skipping {pair} — no data")
            continue

        df = build_features(df)
        print(f"  Candles: {len(df)}")
        print(f"  Date range: {df['ts'].min()} → {df['ts'].max()}")
        print(f"  Positive rate: {df['label'].mean()*100:.1f}%")

        X = df[FEATURE_COLS].values
        y = df["label"].values

        # Preprocessing
        scaler = MinMaxScaler(feature_range=(-1, 1))
        X_scaled = scaler.fit_transform(X)

        # Model (matches experiment hyperparameters)
        model = XGBClassifier(
            objective="binary:logistic",
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            random_state=1,
            verbosity=0,
            eval_metric="logloss",
        )
        model.fit(X_scaled, y)

        # Probability distribution
        p = model.predict_proba(X_scaled)[:, 1]
        print(f"\n  Training predictions:")
        print(f"    Mean:  {p.mean():.4f}")
        print(f"    Std:   {p.std():.4f}")
        print(f"    Min:   {p.min():.4f}")
        print(f"    Max:   {p.max():.4f}")
        print(f"    %>55:  {(p >= 0.55).mean()*100:.1f}%")
        print(f"    %>50:  {(p >= 0.50).mean()*100:.1f}%")

        # Save model + scaler
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_pair = pair.replace("/", "_")
        model_name = f"leah_v4_4_{safe_pair}_xgb_clf"
        model_path = OUTPUT_DIR / f"{model_name}.pkl"
        scaler_path = OUTPUT_DIR / f"{model_name}_scaler.pkl"

        joblib.dump(model, model_path)
        joblib.dump(scaler, scaler_path)

        # Metadata
        meta = {
            "version": "v4.4",
            "pair": pair,
            "date": timestamp,
            "n_samples": int(len(df)),
            "positive_rate": float(df["label"].mean()),
            "features": FEATURE_COLS,
            "n_features": len(FEATURE_COLS),
            "hyperparameters": {
                "objective": "binary:logistic",
                "n_estimators": 200,
                "max_depth": 4,
                "learning_rate": 0.05,
                "random_state": 1,
                "eval_metric": "logloss",
            },
            "training": {
                "date_from": str(df["ts"].min()),
                "date_to": str(df["ts"].max()),
            },
            "prediction_distribution": {
                "mean": float(p.mean()),
                "std": float(p.std()),
                "min": float(p.min()),
                "max": float(p.max()),
                "pct_above_55": float((p >= 0.55).mean()),
                "pct_above_50": float((p >= 0.50).mean()),
            },
            "source": "experiment_e_walkforward_15f_stable",
            "experiments_validated": ["A", "D", "E"],
            "notes": [
                "15-feature XGBClassifier; validated vs 28-feature in Experiment E",
                "Walk-forward AUC 0.6247 vs 0.6045 baseline; 13/18 folds won",
                "Deploy after shadow mode + paper trading validation",
            ],
        }

        meta_path = OUTPUT_DIR / f"{model_name}_meta.json"
        meta_path.write_text(json.dumps(meta, indent=2))

        print(f"\n  Saved:")
        print(f"    Model:  {model_path}")
        print(f"    Scaler: {scaler_path}")
        print(f"    Meta:   {meta_path}")

    print(f"\n{'='*60}")
    print("Retrain complete. Next: update LeahAI to use v4.4 model.")
    print("=" * 60)
