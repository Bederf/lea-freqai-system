"""
replay_engine.py — Leah Evaluation Harness
Replay engine for candle-level trade simulation using archived feather data.
"""

from __future__ import annotations
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

# Import feature builder from the main system
import sys
sys.path.insert(0, "/home/shad/lea-freqai-system")
from retrain_15f_classifier import build_features, FEATURE_COLS


# ─── Trade simulation ──────────────────────────────────────────────────────────

class CandleReplayEngine:
    """
    Replay engine that simulates trade entries and exits on historical candle data
    given a trained model and entry/exit configuration.

    Entry logic:
        - P(vol expansion) >= probability_threshold
        - Optional: btc_trend_filter (0 = disabled, or min correlation)
        - Optional: ema_filter (None, 'ema20', 'ema50', 'ema100')
        - Optional: close > ema

    Exit logic (fixed as per current strategy):
        - Realized profit calculated from open to next candle's close
        - No stacking: one open trade at a time, no re-entry until exit
        - Flat fees: fee_open_pct + fee_close_pct deducted from net_profit
    """

    def __init__(
        self,
        pair: str,
        model,
        scaler,
        feature_names: list[str],
        fee_open_pct: float = 0.001,
        fee_close_pct: float = 0.001,
        stake: float = 1.0,
    ):
        self.pair = pair
        self.model = model
        self.scaler = scaler
        self.feature_names = feature_names
        self.fee_open_pct = fee_open_pct
        self.fee_close_pct = fee_close_pct
        self.stake = stake

    def simulate(
        self,
        candles: pd.DataFrame,
        probability_threshold: float = 0.55,
        btc_trend_filter: float = 0.0,
        ema_filter: str | None = None,
        require_close_above_ema: bool = True,
        position_size_pct: float = 1.0,
        btc_candles: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        Run the replay simulation on a candle DataFrame.

        Parameters
        ----------
        candles : DataFrame
            Must have OHLCV columns.
        probability_threshold : float
            Entry gate: P(vol expansion) >= threshold.
        btc_trend_filter : float
            Minimum Pearson correlation between pair close and BTC close over
            the lookback window (e.g. 0.0 = disabled).
        ema_filter : str or None
            EMA period to check: 'ema20', 'ema50', 'ema100'.
        require_close_above_ema : bool
            Whether close must be above EMA (True) or below (False).
        position_size_pct : float
            Fraction of stake to use (1.0 = full stake).
        btc_candles : DataFrame, optional
            BTC candles for trend filter correlation.

        Returns
        -------
        trades DataFrame with columns:
            entry_time, exit_time, entry_price, exit_price,
            net_profit, is_win, mfe_pct, mae_pct, holding_minutes,
            probability, outcome (1 = vol expansion, 0 = no)
        """
        df = candles.copy()
        df = df.reset_index(drop=True)

        # Build features
        try:
            df = build_features(df)
        except Exception:
            return pd.DataFrame()

        # Compute EMA if needed
        if ema_filter is not None:
            period = int(ema_filter.replace("ema", ""))
            df[f"ema_{period}"] = df["close"].ewm(span=period, adjust=False).mean()

        # Compute BTC trend filter if needed
        if btc_trend_filter > 0 and btc_candles is not None:
            btc_aligned = btc_candles.copy().reset_index(drop=True)
            # Align by length
            min_len = min(len(df), len(btc_aligned))
            df = df.iloc[-min_len:].reset_index(drop=True)
            btc_aligned = btc_aligned.iloc[-min_len:].reset_index(drop=True)

            corr = df["close"].corr(btc_aligned["close"]) if len(df) > 5 else 0.0
            use_btc_filter = corr >= btc_trend_filter
        else:
            use_btc_filter = True

        if not use_btc_filter:
            return pd.DataFrame()

        # Compute probability predictions
        feature_df = df[FEATURE_COLS].copy()

        # Handle NaN/Inf
        feature_df = feature_df.replace([np.inf, -np.inf], np.nan)
        feature_df = feature_df.fillna(0)

        try:
            X = self.scaler.transform(feature_df.values)
            probs = self.model.predict_proba(X)[:, 1]
        except Exception:
            return pd.DataFrame()

        df["probability"] = probs

        # Apply EMA filter
        if ema_filter is not None:
            period = int(ema_filter.replace("ema", ""))
            ema_col = f"ema_{period}"
            if ema_col in df.columns:
                if require_close_above_ema:
                    df["ema_ok"] = df["close"] > df[ema_col]
                else:
                    df["ema_ok"] = df["close"] < df[ema_col]
            else:
                df["ema_ok"] = True
        else:
            df["ema_ok"] = True

        df["prob_gate"] = df["probability"] >= probability_threshold

        # ─── Simulate trades (no stacking) ─────────────────────────────────
        trades = []
        in_trade = False
        entry_idx = None
        entry_price = None

        for i in range(len(df)):
            row = df.iloc[i]

            if not in_trade:
                # Entry logic
                if row["prob_gate"] and row["ema_ok"]:
                    in_trade = True
                    entry_idx = i
                    entry_price = row["close"]
                    entry_prob = row["probability"]
            else:
                # Exit logic: next signal candle close
                exit_price = row["close"]
                outcome = int(row["target"]) if "target" in df.columns else int(row.get("&-target", 0))

                net = self._compute_pnl(
                    entry_price, exit_price,
                    self.fee_open_pct, self.fee_close_pct,
                    self.stake * position_size_pct,
                    outcome,
                )

                holding_minutes = (df.iloc[i]["open_time"] - df.iloc[entry_idx]["open_time"]).total_seconds() / 60 if "open_time" in df.columns else 5

                # MFE / MAE: track intra-trade high/low
                mfe = ((exit_price - entry_price) / entry_price * 100) if outcome == 1 else 0
                mae = ((entry_price - exit_price) / entry_price * 100) if outcome == 0 else 0

                trades.append({
                    "entry_time": df.iloc[entry_idx]["open_time"] if "open_time" in df.columns else entry_idx,
                    "exit_time": df.iloc[i]["open_time"] if "open_time" in df.columns else i,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "net_profit": net,
                    "is_win": net > 0,
                    "mfe_pct": max(mfe, 0),
                    "mae_pct": max(mae, 0),
                    "holding_minutes": holding_minutes,
                    "probability": entry_prob,
                    "outcome": outcome,
                })
                in_trade = False
                entry_idx = None

        if trades:
            return pd.DataFrame(trades)
        return pd.DataFrame()

    @staticmethod
    def _compute_pnl(
        entry_price: float,
        exit_price: float,
        fee_open_pct: float,
        fee_close_pct: float,
        stake: float,
        outcome: int,
    ) -> float:
        """
        Compute P&L for a trade.
        - outcome=1: win → exit_price > entry_price
        - outcome=0: loss → exit_price < entry_price
        Fees deducted from gross P&L.
        """
        if entry_price <= 0 or exit_price <= 0:
            return -stake * fee_open_pct - stake * fee_close_pct

        gross_return = (exit_price - entry_price) / entry_price
        gross_pnl = stake * gross_return
        fees = stake * (fee_open_pct + fee_close_pct)

        return gross_pnl - fees


# ─── Replay from pre-computed fold probabilities ──────────────────────────────

def replay_from_fold_probs(
    fold_results: list[dict],
    thresholds: list[float],
    fee_pct: float = 0.002,
) -> pd.DataFrame:
    """
    Given pre-computed fold results (from WalkForwardRunner.folds),
    compute threshold sweep metrics across all folds.

    Each fold has: prob_mean, prob_std, above_55, above_50, fold_auc, etc.
    We use the distribution statistics to reconstruct an approximate trade list.

    For a proper sweep we need the actual probability array per test candle.
    This function uses the aggregate stats as a fast approximation.
    """
    records = []

    for thresh in thresholds:
        total_trades = 0
        total_wins = 0
        total_pnl = 0.0
        all_pnls = []

        for fold in fold_results:
            prob_mean = fold["prob_mean"]
            prob_std = fold["prob_std"]
            n = fold["test_n"]
            positive_rate = fold["test_positive_rate"]

            # Estimate trade count at this threshold
            # Using normal approximation of the probability distribution
            z = (thresh - prob_mean) / prob_std if prob_std > 0 else -999
            import math
            trade_rate = 1 - _norm_cdf(z) if prob_std > 0 else 0.0
            n_trades = max(int(n * trade_rate), 0)

            if n_trades == 0:
                continue

            # Estimate win rate: base rate conditioned on P >= threshold
            # P(win | P >= thresh) = P(P >= thresh | win) * P(win) / P(P >= thresh)
            # Approximate: use positive_rate as base win rate, shift up
            p_pass = trade_rate
            # Conservative: assume win rate scales proportionally
            est_win_rate = min(positive_rate / p_pass, 1.0) if p_pass > 0 else 0.5
            est_win_rate = max(est_win_rate, 0.3)  # floor at 30% for high thresholds

            n_wins = int(n_trades * est_win_rate)
            n_losses = n_trades - n_wins

            # P&L per trade
            gross_win = 1 - fee_pct
            gross_loss = -(1 + fee_pct)
            trade_pnl = n_wins * gross_win + n_losses * gross_loss

            total_trades += n_trades
            total_wins += n_wins
            total_pnl += trade_pnl
            for _ in range(n_wins):
                all_pnls.append(gross_win)
            for _ in range(n_losses):
                all_pnls.append(gross_loss)

        if total_trades == 0:
            continue

        # Running P&L for drawdown
        cum_pnl = np.cumsum(pnl_series)
        peak = np.maximum.accumulate(cum_pnl)
        dd = cum - peak
        max_dd = dd.min()
        max_dd_pct = max_dd / (np.maximum.accumulate(cum).max() + 1e-9) * 100

        win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0
        avg_win = gross_win
        avg_loss = abs(gross_loss)
        pf = (total_wins * avg_win) / (max(abs(total_trades - total_wins) * avg_loss, 1e-9))
        expectancy = total_pnl / total_trades if total_trades > 0 else 0

        records.append({
            "threshold": thresh,
            "trades": total_trades,
            "wins": total_wins,
            "losses": total_trades - total_wins,
            "win_rate_pct": round(win_rate, 2),
            "avg_win": round(avg_win, 6),
            "avg_loss": round(avg_loss, 6),
            "gross_profit": round(total_wins * avg_win, 4),
            "gross_loss": round((total_trades - total_wins) * avg_loss, 4),
            "profit_factor": round(pf, 3),
            "total_pnl": round(total_pnl, 4),
            "expectancy": round(expectancy, 6),
            "max_drawdown": round(max_dd, 4),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "mfe_mean": 0.0,
            "mae_mean": 0.0,
            "median_trade": round(float(np.median(all_pnls)), 4),
            "breakeven_win_rate": round(avg_loss / (avg_win + avg_loss) * 100, 2),
        })

    return pd.DataFrame(records)


def _norm_cdf(x: float) -> float:
    """Approximate normal CDF."""
    import math
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
