#!/usr/bin/env python3
"""
E001c — Strategy Execution Replay: 0.55 vs 0.65
==================================================
Full trading simulation with actual Leah v4 entry/exit mechanics:

ENTRY GATES:
  1. v4.4 probability >= threshold
  2. BTC trend >= 0.002
  3. close > EMA50

EXIT RULES:
  1. ROI ladder: 5% (immediate), 3% (30min), 2% (60min), 1% (120min trailing floor)
  2. Stoploss: -5%
  3. Time exit: if underwater after 6h, exit

POSITION SIZING:
  confidence_multiplier = clip(1.0 + (prob - threshold) * 2.5, 0.5, 1.5)
  stake = proposed_stake * confidence_multiplier

Compares ONLY 0.55 vs 0.65 — one variable at a time.
"""

import gc, joblib, pickle, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

# Container paths
DATA_DIR   = Path("/freqtrade/user_data/data/binance")
MODEL_DIR  = Path("/freqtrade/user_data/models")
FOLD_DATA  = Path("/freqtrade/user_data/reports/experiments/expE_BTC_20260711_211246.csv")
OUTPUT_DIR = Path("/freqtrade/user_data/reports/e001c")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, "/freqtrade/user_data")
from retrain_15f_classifier import build_features, FEATURE_COLS

from core.metrics import rank_thresholds
from core.reporting import generate_html_report

PAIRS      = ["BTC", "ETH", "SOL", "LINK"]
PAIR_FILES = {"BTC": "BTC_USDT", "ETH": "ETH_USDT", "SOL": "SOL_USDT", "LINK": "LINK_USDT"}
THRESHOLDS = [0.55, 0.65]   # only comparing the two candidates
TRAIN_N    = 8640
TEST_N     = 2016
FEE_PCT    = 0.001

# ROI ladder (matches LeahAI.py minimal_roi)
ROI_LADDER = [
    (0,    0.05),   # immediate: 5%
    (30,   0.03),   # 30min: 3%
    (60,   0.02),   # 60min: 2%
    (120,  0.01),   # 120min+: 1% (floor)
]
STOPLOSS_PCT   = -0.05
TIME_EXIT_HRS  = 6.0   # exit if underwater after 6h

# EMA period
EMA_PERIOD = 50


# ─── Helpers ──────────────────────────────────────────────────────────────────

def compute_ema(series, period):
    """Compute EMA from a series."""
    ema = series.ewm(span=period, adjust=False).mean()
    return ema


def load_pair_candles(pair, fold_end, test_n=TEST_N):
    """Load test-window candles for pair and compute indicators."""
    pf = PAIR_FILES[pair]
    feather = DATA_DIR / f"{pf}-5m.feather"
    if not feather.exists():
        return None, None

    df = pd.read_feather(feather).rename(columns={"date": "open_time"})
    df = df.sort_values("open_time").reset_index(drop=True)

    # Split at fold end
    fold_end_ts = pd.to_datetime(fold_end)
    if fold_end_ts.tz is None:
        fold_end_ts = fold_end_ts.tz_localize("UTC")
    split_idx = df[df["open_time"] >= fold_end_ts].index
    if len(split_idx) == 0:
        return None, None
    si = split_idx[0]

    test_start = si
    test_end   = min(si + test_n, len(df))
    if test_end - test_start < 100:
        return None, None

    df = df.iloc[test_start:test_end].copy().reset_index(drop=True)

    # Build features + model probability
    df = build_features(df)
    feat_df = df[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(0)
    model, scaler = load_model(pair)
    if model is None or scaler is None:
        return None, None
    try:
        probs = model.predict_proba(scaler.transform(feat_df.values))[:, 1]
    except Exception:
        return None, None

    df["probability"] = probs
    df["ema_50"] = compute_ema(df["close"], EMA_PERIOD)

    return df, model


def load_btc_trend_series(fold_end, test_n=TEST_N):
    """Load BTC close series for the same test window to compute trend filter."""
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
    # BTC trend = % return over last ~5 candles (5m × 5 = 25min)
    # Matches strategy's %btc_trend approximation
    btc["btc_trend"] = btc["close"].pct_change(5)
    return btc[["open_time", "close", "btc_trend"]]


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
                folds.append({
                    "fold_end":   row["fold_end"],
                    "prob_mean":  float(row["prob_mean"]),
                    "prob_std":   float(row["prob_std"]),
                })
    return folds


# ─── Core trading simulation ───────────────────────────────────────────────────

def simulate_trades(
    pair_df,
    btc_df,
    threshold,
    fee_pct=FEE_PCT,
    roi_ladder=ROI_LADDER,
    stoploss_pct=STOPLOSS_PCT,
    time_exit_hrs=TIME_EXIT_HRS,
    stake=1.0,
):
    """
    Simulate trades with Leah v4 entry/exit mechanics.

    Returns list of trade dicts.
    """
    # Merge BTC trend into pair_df
    if btc_df is not None:
        pair_df = pair_df.copy()
        pair_df["btc_trend"] = btc_df["btc_trend"].reindex(pair_df.index, method="ffill").fillna(0)
    else:
        pair_df = pair_df.copy()
        pair_df["btc_trend"] = 0.0

    n = len(pair_df)
    trades = []
    in_trade = False

    # Trade state
    entry_idx = None
    entry_price = None
    entry_prob = None
    entry_time = None

    for i in range(n):
        row = pair_df.iloc[i]

        if not in_trade:
            # ── ENTRY GATES ──────────────────────────────────────────────────
            # Gate 1: probability threshold
            if row["probability"] < threshold:
                continue
            # Gate 2: BTC trend >= 0.002
            if row.get("btc_trend", 0) < 0.002:
                continue
            # Gate 3: close > EMA50
            if row["ema_50"] > 0 and row["close"] <= row["ema_50"]:
                continue

            # Entry approved
            in_trade = True
            entry_idx = i
            entry_price = row["close"]
            entry_prob = row["probability"]
            entry_time = row["open_time"]

        else:
            # ── EXIT EVALUATION ─────────────────────────────────────────────
            current_price = row["close"]
            current_time  = row["open_time"]

            # Duration — fix tz-aware timedelta arithmetic
            try:
                entry_t = entry_time
                curr_t  = current_time
                # Ensure both are tz-aware Timestamps
                if hasattr(entry_t, 'tz') and entry_t.tz is None:
                    entry_t = entry_t.tz_localize("UTC")
                if hasattr(curr_t, 'tz') and curr_t.tz is None:
                    curr_t = curr_t.tz_localize("UTC")
                dt_min = (curr_t - entry_t).total_seconds() / 60.0
            except Exception:
                dt_min = 0.0

            current_profit = (current_price - entry_price) / entry_price
            exited = False
            exit_reason = None
            exit_price = current_price

            # Exit 1: ROI reached — use ladder
            for cutoff_min, roi_pct in reversed(roi_ladder):
                if dt_min >= cutoff_min and current_profit >= roi_pct:
                    exited = True
                    exit_reason = f"roi_{roi_pct}"
                    break

            # Exit 2: Stoploss
            if not exited and current_profit <= stoploss_pct:
                exited = True
                exit_reason = "stoploss"

            # Exit 3: Time exit — if underwater after 6h
            if not exited and dt_min > time_exit_hrs * 60 and current_profit < 0:
                exited = True
                exit_reason = "time_exit_6h_negative"

            if exited:
                # P&L
                gross_ret = (exit_price - entry_price) / entry_price
                # Fee on entry + exit
                net_pnl = stake * gross_ret - stake * fee_pct * 2
                # Confidence multiplier for position sizing
                conf_mult = np.clip(1.0 + (entry_prob - threshold) * 2.5, 0.5, 1.5)
                net_pnl *= conf_mult

                trades.append({
                    "entry_time":   entry_time,
                    "exit_time":    current_time,
                    "duration_min": dt_min,
                    "entry_price":  entry_price,
                    "exit_price":   exit_price,
                    "gross_return": gross_ret,
                    "net_pnl":      net_pnl,
                    "is_win":       net_pnl > 0,
                    "exit_reason":  exit_reason,
                    "probability":  entry_prob,
                    "confidence_mult": conf_mult,
                    "current_profit_at_exit": current_profit,
                })
                in_trade = False

    return trades


# ─── Run ─────────────────────────────────────────────────────────────────────

import pandas as pd
import numpy as np

def run():
    folds = load_folds()
    print(f"E001c — Strategy Execution Replay")
    print(f"Folds: {len(folds)}  Pairs: {PAIRS}  Thresholds: {THRESHOLDS}")
    print()

    # Accumulate: {thresh: {pair: [pnl1, pnl2, ...]}}
    all_trades = {t: [] for t in THRESHOLDS}

    for pair in PAIRS:
        print(f"── {pair} ──")
        for fold in folds:
            pair_df, _ = load_pair_candles(pair, fold["fold_end"])
            if pair_df is None:
                continue
            btc_df = load_btc_trend_series(fold["fold_end"])
            for thresh in THRESHOLDS:
                trades = simulate_trades(pair_df, btc_df, thresh)
                all_trades[thresh].extend(trades)
            gc.collect()

    print("\n" + "=" * 70)
    print("E001c — STRATEGY EXECUTION REPLAY RESULTS")
    print("=" * 70)

    records = []
    for thresh in THRESHOLDS:
        trades = all_trades[thresh]
        if not trades:
            records.append({"threshold": thresh, "trades": 0,
                "wins": 0, "losses": 0, "win_rate_pct": 0,
                "avg_win": 0, "avg_loss": 0, "gross_profit": 0,
                "gross_loss": 0, "profit_factor": 0, "total_pnl": 0,
                "expectancy": 0, "max_drawdown": 0, "max_drawdown_pct": 0,
                "median_trade": 0, "breakeven_win_rate": 0, "cagr": 0,
                "avg_duration_min": 0})
            continue

        tdf = pd.DataFrame(trades)
        n   = len(tdf)
        wins  = int((tdf["net_pnl"] > 0).sum())
        loss  = n - wins
        tp    = float(tdf["net_pnl"].sum())
        wr    = wins / n * 100
        aw    = float(tdf.loc[tdf["net_pnl"] > 0, "net_pnl"].mean()) if wins > 0 else 0.0
        al    = abs(float(tdf.loc[tdf["net_pnl"] <= 0, "net_pnl"].mean())) if loss > 0 else 0.0
        gp    = float(tdf.loc[tdf["net_pnl"] > 0, "net_pnl"].sum())
        gl    = abs(float(tdf.loc[tdf["net_pnl"] <= 0, "net_pnl"].sum()))
        pf    = gp / max(gl, 1e-9)
        exp   = tp / n
        cum   = np.cumsum(tdf["net_pnl"].values)
        peak  = np.maximum.accumulate(cum)
        dd    = cum - peak
        max_dd = float(dd.min())
        max_dd_pct = abs(max_dd) / (peak.max() + 1e-9) * 100 if peak.max() > 0 else 0
        be    = al / (aw + al) * 100 if (aw + al) > 0 else 0.0
        avg_dur = float(tdf["duration_min"].mean())

        # Approximate CAGR: assume 1 unit stake, 18 folds × 7 days = 126 days
        days = len(folds) * 7
        cagr = ((1 + tp) ** (365 / days) - 1) * 100 if days > 0 else 0

        print(
            f"  thresh={thresh:.2f}  n={n:5d}  WR={wr:.1f}%  "
            f"PF={pf:.3f}  E={exp:+.5f}  DD%={max_dd_pct:.1f}%  "
            f"CAGR={cagr:.1f}%  avg_dur={avg_dur:.0f}min"
        )

        records.append({
            "threshold": thresh, "trades": n, "wins": wins, "losses": loss,
            "win_rate_pct": round(wr, 2), "avg_win": round(aw, 5),
            "avg_loss": round(al, 5), "gross_profit": round(gp, 3),
            "gross_loss": round(gl, 3), "profit_factor": round(pf, 3),
            "total_pnl": round(tp, 3), "expectancy": round(exp, 5),
            "max_drawdown": round(max_dd, 3), "max_drawdown_pct": round(max_dd_pct, 2),
            "median_trade": round(float(np.median(tdf["net_pnl"])), 5),
            "breakeven_win_rate": round(be, 2),
            "cagr": round(cagr, 2), "avg_duration_min": round(avg_dur, 1),
        })

    df = pd.DataFrame(records)

    # Recommendation logic
    best = df.loc[df["expectancy"].idxmax()] if len(df) > 0 else None
    if best is not None and best["expectancy"] > 0 and best["profit_factor"] > 1.0:
        winner = best["threshold"]
        recommendation = (
            f"Threshold {winner:.2f} is superior in net profit ({best['total_pnl']:+.3f}), "
            f"expectancy ({best['expectancy']:+.5f}), and profit factor ({best['profit_factor']:.3f}). "
            f"Promote to paper trading."
        )
    else:
        recommendation = (
            "No threshold meets all acceptability criteria. "
            f"Best expectancy: {best['threshold']:.2f} ({best['expectancy']:+.5f}). "
            "Verify with live paper trading before promotion."
        )

    manifest = {
        "experiment_id": "E001c", "title": "Strategy Execution Replay: 0.55 vs 0.65",
        "hypothesis": "0.65 produces superior trading performance vs 0.55 under identical entry/exit mechanics.",
        "null_hypothesis": "No difference in trading performance between 0.55 and 0.65.",
        "decision_metric": "net_profit",
        "secondary_metrics": ["expectancy", "profit_factor", "max_drawdown_pct", "cagr", "win_rate"],
        "status": "completed",
        "method": "strategy_execution_replay",
        "pairs": PAIRS,
        "fee_pct": FEE_PCT,
        "folds_per_pair": len(folds),
        "roi_ladder": str(ROI_LADDER),
        "stoploss": str(STOPLOSS_PCT),
        "time_exit_hrs": str(TIME_EXIT_HRS),
    }
    params = {
        "thresholds": "0.55 vs 0.65",
        "model": "C (15 stable features) — v4.4",
        "pairs": ", ".join(PAIRS),
        "fee_pct": str(FEE_PCT),
        "method": "strategy_execution_replay",
        "entry_gates": "prob + BTC_trend + EMA50",
        "roi_ladder": str(ROI_LADDER),
        "stoploss": str(STOPLOSS_PCT),
        "time_exit": f"{TIME_EXIT_HRS}h if underwater",
    }

    path = generate_html_report(
        "E001c", "Strategy Execution Replay",
        manifest["hypothesis"], manifest["null_hypothesis"],
        params, df, best, recommendation,
        manifest, str(OUTPUT_DIR),
    )
    print(f"\nReport: {path}")

    # Also save detailed trade log
    import csv
    trade_log_path = OUTPUT_DIR / f"E001c_trades_{pd.Timestamp.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    all_rows = []
    for thresh in THRESHOLDS:
        for t in all_trades[thresh]:
            all_rows.append({"threshold": thresh, **t})
    if all_rows:
        td = pd.DataFrame(all_rows)
        td.to_csv(trade_log_path, index=False)
        print(f"Trade log: {trade_log_path}")

    return df, best, recommendation


if __name__ == "__main__":
    run()
