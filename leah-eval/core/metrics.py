"""
metrics.py — Leah Evaluation Harness
Metrics computation engine for replay-based strategy evaluation.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import TypedDict


class TradeMetrics(TypedDict):
    trades: int
    wins: int
    losses: int
    win_rate: float
    avg_win: float
    avg_loss: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    total_pnl: float
    expectancy: float
    expectancy_per_trade: float
    max_drawdown: float
    max_drawdown_pct: float
    cagr: float | None
    mfe_mean: float
    mae_mean: float
    median_trade: float
    breakeven_win_rate: float
    avg_holding_minutes: float | None
    open_trades: int


def compute_trade_metrics(
    trades: pd.DataFrame,
    stake_amount: float = 1.0,
    fee_open_pct: float = 0.001,
    fee_close_pct: float = 0.001,
    annualize_trades: int = 105120,  # 5-min cycles per year per pair
    n_pairs: int = 1,
) -> TradeMetrics:
    """
    Compute full metrics suite from a replay trade log.

    Parameters
    ----------
    trades : DataFrame
        Must contain columns: net_profit, is_win, open_date, close_date,
        mfe_pct, mae_pct, holding_minutes, is_open
    stake_amount : float
        Not used here — net_profit should already be in absolute terms.
    fee_open_pct, fee_close_pct : float
        Not used — fees should be pre-deducted in net_profit.
    annualize_trades : int
        5-min cycles per year per pair for CAGR estimation.
    n_pairs : int
        Number of pairs in the simulation.
    """
    closed = trades[trades.get("is_open", pd.Series(False)) == False].copy()
    open_trades = trades[trades.get("is_open", pd.Series(False)) == True]

    if closed.empty:
        return TradeMetrics(
            trades=0, wins=0, losses=0, win_rate=0.0,
            avg_win=0.0, avg_loss=0.0, gross_profit=0.0, gross_loss=0.0,
            profit_factor=0.0, total_pnl=0.0, expectancy=0.0,
            expectancy_per_trade=0.0, max_drawdown=0.0, max_drawdown_pct=0.0,
            cagr=None, mfe_mean=0.0, mae_mean=0.0, median_trade=0.0,
            breakeven_win_rate=0.0, avg_holding_minutes=None, open_trades=len(open_trades),
        )

    wins = closed[closed["is_win"]]
    losses = closed[~closed["is_win"]]

    total_pnl = closed["net_profit"].sum()
    win_rate = len(wins) / len(closed) * 100 if len(closed) > 0 else 0.0
    avg_win = wins["net_profit"].mean() if len(wins) > 0 else 0.0
    avg_loss = abs(losses["net_profit"].mean()) if len(losses) > 0 else 0.0
    gross_profit = wins["net_profit"].sum() if len(wins) > 0 else 0.0
    gross_loss = abs(losses["net_profit"].sum()) if len(losses) > 0 else 0.0

    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    expectancy = closed["net_profit"].mean() if len(closed) > 0 else 0.0

    # Drawdown
    closed_s = closed.sort_values("close_date").reset_index(drop=True) if "close_date" in closed.columns else closed.reset_index(drop=True)
    if "close_date" in trades.columns:
        closed_s["cum_pnl"] = closed_s["net_profit"].cumsum()
        closed_s["peak"] = closed_s["cum_pnl"].cummax()
        closed_s["drawdown"] = closed_s["cum_pnl"] - closed_s["peak"]
        max_drawdown = closed_s["drawdown"].min()
        max_drawdown_pct = max_drawdown / (closed_s["peak"].cummax() + 1e-9) * 100
    else:
        max_drawdown = total_pnl
        max_drawdown_pct = 0.0

    # CAGR
    if "close_date" in closed.columns and len(closed) > 1:
        start_date = closed["close_date"].min()
        end_date = closed["close_date"].max()
        years = max((end_date - start_date).days / 365.25, 1 / 365.25)
        n_annual = annualize_trades * n_pairs
        scale = n_annual / max(len(closed), 1)
        cagr = (1 + total_pnl / max(abs(max_drawdown), 1e-9)) ** (1 / years) - 1 if max_drawdown != 0 else total_pnl
        cagr = None  # de-facto meaningless on small N; return None
    else:
        cagr = None

    # Breakeven win rate
    breakeven_wr = 0.0
    if avg_loss > 0 and avg_win > 0:
        breakeven_wr = avg_loss / (avg_win + avg_loss) * 100

    # MFE / MAE
    mfe_mean = closed["mfe_pct"].mean() if "mfe_pct" in closed.columns else 0.0
    mae_mean = closed["mae_pct"].mean() if "mae_pct" in closed.columns else 0.0

    # Median trade
    median_trade = closed["net_profit"].median() if len(closed) > 0 else 0.0

    # Avg holding time
    avg_hold = None
    if "holding_minutes" in closed.columns:
        avg_hold = closed["holding_minutes"].mean()

    return TradeMetrics(
        trades=len(closed),
        wins=len(wins),
        losses=len(losses),
        win_rate=round(win_rate, 2),
        avg_win=round(avg_win, 6),
        avg_loss=round(avg_loss, 6),
        gross_profit=round(gross_profit, 6),
        gross_loss=round(gross_loss, 6),
        profit_factor=round(profit_factor, 3) if profit_factor != float("inf") else float("inf"),
        total_pnl=round(total_pnl, 6),
        expectancy=round(expectancy, 6),
        expectancy_per_trade=round(expectancy, 6),
        max_drawdown=round(max_drawdown, 6),
        max_drawdown_pct=round(max_drawdown_pct, 2),
        cagr=round(cagr, 4) if cagr is not None else None,
        mfe_mean=round(mfe_mean, 4),
        mae_mean=round(mae_mean, 4),
        median_trade=round(median_trade, 6),
        breakeven_win_rate=round(breakeven_wr, 2),
        avg_holding_minutes=round(avg_hold, 2) if avg_hold is not None else None,
        open_trades=len(open_trades),
    )


def compute_threshold_sweep(
    probabilities: np.ndarray,
    targets: np.ndarray,
    thresholds: list[float],
    fees: float = 0.002,
) -> pd.DataFrame:
    """
    Given arrays of predicted probabilities and binary realized outcomes,
    compute metrics at each threshold level.

    This is used for walk-forward fold evaluation where we have
    probability predictions and realized outcomes (1 = vol expansion, 0 = no).

    Parameters
    ----------
    probabilities : ndarray
        P(vol expansion) per candle, shape (n,)
    targets : ndarray
        Realized outcome per candle, shape (n,)
    thresholds : list of floats
        Thresholds to sweep.
    fees : float
        Estimated round-trip fees as fraction of notional (e.g. 0.002 = 0.2%)

    Returns
    -------
    DataFrame with one row per threshold and columns:
        threshold, trades, wins, losses, win_rate_pct, avg_win, avg_loss,
        gross_profit, gross_loss, profit_factor, total_pnl, expectancy,
        max_drawdown, max_drawdown_pct, mfe_mean, mae_mean
    """
    records = []

    for thresh in thresholds:
        # Signal: predict 1 iff P >= threshold
        signals = (probabilities >= thresh).astype(int)

        # Only candles where we have a signal count as "trades"
        # For a candle-level simulation: trade = 1 signal candle
        # Outcome = realized target at that candle
        signal_idx = np.where(signals == 1)[0]
        n_trades = len(signal_idx)

        if n_trades == 0:
            records.append({
                "threshold": thresh, "trades": 0, "wins": 0, "losses": 0,
                "win_rate_pct": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "gross_profit": 0.0, "gross_loss": 0.0,
                "profit_factor": 0.0, "total_pnl": 0.0, "expectancy": 0.0,
                "max_drawdown": 0.0, "max_drawdown_pct": 0.0,
                "mfe_mean": 0.0, "mae_mean": 0.0, "median_trade": 0.0,
                "breakeven_win_rate": 0.0,
            })
            continue

        outcomes = targets[signal_idx]
        wins_idx = np.where(outcomes == 1)[0]
        losses_idx = np.where(outcomes == 0)[0]

        # P&L: assume fixed reward of +1 per unit for wins, -1 for losses, minus fees
        win_pnl = len(wins_idx) * (1 - fees)
        loss_pnl = -len(losses_idx) * (1 + fees)
        trade_pnl = win_pnl + loss_pnl

        gross_profit = win_pnl
        gross_loss = abs(loss_pnl)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        expectancy = trade_pnl / n_trades
        win_rate = len(wins_idx) / n_trades * 100

        avg_win = win_pnl / len(wins_idx) if len(wins_idx) > 0 else 0.0
        avg_loss = abs(loss_pnl / len(losses_idx)) if len(losses_idx) > 0 else 0.0

        # Running P&L and drawdown
        pnl_series = np.array([(1 - fees) if o == 1 else -(1 + fees) for o in outcomes])
        cum_pnl = np.cumsum(pnl_series)
        peak = np.cummax(cum_pnl)
        drawdown = cum_pnl - peak
        max_dd = drawdown.min()
        max_dd_pct = max_dd / (np.maximum.accumulate(cum_pnl).max() + 1e-9) * 100

        records.append({
            "threshold": thresh,
            "trades": n_trades,
            "wins": len(wins_idx),
            "losses": len(losses_idx),
            "win_rate_pct": round(win_rate, 2),
            "avg_win": round(avg_win, 6),
            "avg_loss": round(avg_loss, 6),
            "gross_profit": round(gross_profit, 6),
            "gross_loss": round(gross_loss, 6),
            "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else float("inf"),
            "total_pnl": round(trade_pnl, 6),
            "expectancy": round(expectancy, 6),
            "max_drawdown": round(max_dd, 6),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "mfe_mean": 0.0,
            "mae_mean": 0.0,
            "median_trade": round(np.median(pnl_series), 6),
            "breakeven_win_rate": round(avg_loss / (avg_win + avg_loss) * 100, 2) if avg_win > 0 else 0.0,
        })

    return pd.DataFrame(records)


def rank_thresholds(df: pd.DataFrame, primary_metric: str = "expectancy") -> pd.DataFrame:
    """
    Rank threshold results by primary metric (higher = better).
    Add rank column and recommendation.
    """
    df = df.copy()
    df = df.sort_values(primary_metric, ascending=False).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)

    # Best by primary metric
    best = df.iloc[0]

    # Acceptability criteria
    acceptable = (
        (df["profit_factor"] > 1.0) &
        (df["max_drawdown_pct"] < 50) &
        (df["trades"] >= 10)
    )

    if acceptable.any():
        best_acceptable = df[acceptable].sort_values(primary_metric, ascending=False).iloc[0]
        rec = f"Threshold = {best_acceptable['threshold']} — Highest {primary_metric} among acceptable configs (PF > 1.0, DD < 50%, trades >= 10)"
    else:
        best_acceptable = best
        rec = f"Threshold = {best['threshold']} — No config meets all acceptability criteria; using best {primary_metric}"

    return df, best.to_dict(), rec
