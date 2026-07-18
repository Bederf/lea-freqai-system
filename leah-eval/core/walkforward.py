"""
walkforward.py — Leah Evaluation Harness
Walk-forward validation engine using archived feather data.
"""

from __future__ import annotations
import pickle
from datetime import datetime
from pathlib import Path
from typing import Generator

import numpy as np
import pandas as pd


class WalkForwardRunner:
    """
    Walk-forward cross-validation runner for Leah v4.4.

    Loads pre-computed walk-forward fold results (from experiment E) and
    exposes them as a stream of (fold_end, train_df, test_df, model) tuples.

    Also supports loading raw feather data for full replay.
    """

    def __init__(
        self,
        data_dir: str = "/home/shad/lea-freqai-system/user_data/data/binance",
        model_dir: str = "/home/shad/lea-freqai-system/user_data/models",
        timeframe: str = "5m",
    ):
        self.data_dir = Path(data_dir)
        self.model_dir = Path(model_dir)
        self.timeframe = timeframe
        self.folds = self._load_folds()

    def _load_folds(self) -> list[dict]:
        """
        Load fold metadata from the experiment E CSV.
        """
        import csv

        fold_path = Path("/home/shad/lea-freqai-system/user_data/reports/experiments/expE_BTC_20260711_211246.csv")
        folds = []
        if fold_path.exists():
            with open(fold_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    folds.append({
                        "model": row["model"],
                        "fold_end": row["fold_end"],
                        "train_n": int(row["train_n"]),
                        "test_n": int(row["test_n"]),
                        "test_positive_rate": float(row["test_positive_rate"]),
                        "n_features": int(row["n_features"]),
                        "fold_auc": float(row["fold_auc"]),
                        "fold_brier": float(row["fold_brier"]),
                        "prob_mean": float(row["prob_mean"]),
                        "prob_std": float(row["prob_std"]),
                        "above_55": float(row["above_55"]),
                        "above_50": float(row["above_50"]),
                    })
        return folds

    def get_folds_for_model(self, model_label: str) -> list[dict]:
        """Return all folds for a given model label (e.g. 'C (15 stable)')."""
        return [f for f in self.folds if f["model"] == model_label]

    def iter_fold_candles(
        self,
        pair: str,
        fold_end: str,
        train_window: int = 8640,
        test_window: int = 2016,
    ) -> Generator[tuple[pd.DataFrame, pd.DataFrame], None, None]:
        """
        Load train and test candles for a specific fold.

        Yields (train_df, test_df) for each fold end date.
        """
        feather_path = self.data_dir / pair.replace("/", "_") / f"{self.timeframe}.feather"

        if not feather_path.exists():
            return

        try:
            df = pd.read_feather(feather_path)
        except Exception:
            return

        if "open_time" not in df.columns:
            return

        df = df.sort_values("open_time").reset_index(drop=True)

        # Find fold split point
        fold_end_dt = pd.to_datetime(fold_end).tz_localize("UTC")
        idx = df[df["open_time"] >= fold_end_dt].index[0] if any(df["open_time"] >= fold_end_dt) else len(df)

        train_end = max(0, idx - test_window)
        test_start = train_end
        test_end = min(len(df), train_end + test_window)

        if train_end < train_window:
            return

        train_df = df.iloc[train_end - train_window : train_end].copy()
        test_df = df.iloc[test_start:test_end].copy()

        yield train_df, test_df

    def load_model(self, pair: str, model_label: str) -> tuple:
        """
        Load model and scaler for a pair.

        Returns (model, scaler, feature_names).
        """
        model_name = pair.replace("/", "_")
        model_path = self.model_dir / f"leah_v4_4_{model_name}_xgb_clf_model.pkl"
        scaler_path = self.model_dir / f"leah_v4_4_{model_name}_xgb_clf_scaler.pkl"

        model = scaler = feat_names = None

        if model_path.exists():
            try:
                with open(model_path, "rb") as f:
                    model = pickle.load(f)
            except Exception:
                pass

        if scaler_path.exists():
            try:
                with open(scaler_path, "rb") as f:
                    scaler = pickle.load(f)
            except Exception:
                pass

        # Feature names for v4.4 15-feature model
        feat_names = [
            "vol_ratio_20", "vol_ratio_10", "vol_ratio_5", "vol_ratio_3",
            "vol_ma20", "vol_ma10",
            "pct_ret_1", "pct_ret_3",
            "pct_atr14_rel", "atr14", "hl_range", "candle_body",
            "mom_6", "mom_12", "mom_24",
        ]

        return model, scaler, feat_names

    def summary(self) -> pd.DataFrame:
        """Return fold summary DataFrame."""
        if not self.folds:
            return pd.DataFrame()
        return pd.DataFrame(self.folds)
