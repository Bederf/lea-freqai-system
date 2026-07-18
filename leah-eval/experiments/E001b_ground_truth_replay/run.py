#!/usr/bin/env python3
"""
E001b — Ground-Truth Threshold Replay (container-native)
=========================================================
Runs inside the freqtrade-lea-new container.

Ground-truth candle-level replay: loads feather candles,
builds features with v4.4 logic, runs actual model per fold,
simulates entry at signal candle, exit at next candle close.
"""

import gc, pickle, joblib, sys, warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# Container paths
DATA_DIR   = Path("/freqtrade/user_data/data/binance")
MODEL_DIR  = Path("/freqtrade/user_data/models")
FOLD_DATA  = Path("/freqtrade/user_data/reports/experiments/expE_BTC_20260711_211246.csv")
OUTPUT_DIR = Path("/freqtrade/user_data/reports/e001b")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, "/freqtrade/user_data")
from retrain_15f_classifier import build_features, FEATURE_COLS

from core.metrics import rank_thresholds
from core.reporting import generate_html_report

PAIRS       = ["BTC", "ETH", "SOL", "LINK"]
PAIR_FILES  = {"BTC": "BTC_USDT", "ETH": "ETH_USDT", "SOL": "SOL_USDT", "LINK": "LINK_USDT"}
THRESHOLDS = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
TRAIN_N     = 8640
TEST_N      = 2016
FEE_PCT     = 0.001
STAKE       = 1.0


# ─── Load fold schedule ────────────────────────────────────────────────────────

def load_folds():
    import csv
    folds = []
    with open(FOLD_DATA) as f:
        for row in csv.DictReader(f):
            if row["model"] == "C (15 stable)":
                folds.append({
                    "fold_end":   row["fold_end"],
                    "fold_auc":   float(row["fold_auc"]),
                    "prob_mean":  float(row["prob_mean"]),
                    "prob_std":   float(row["prob_std"]),
                })
    return folds


# ─── Load model + scaler ──────────────────────────────────────────────────────

def load_pair(pair):
    """Load v4.4 model+scaler for a pair."""
    short = pair          # e.g. "BTC"
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


# ─── Single fold replay ────────────────────────────────────────────────────────

def replay_fold(pair, fold, thresholds):
    pf = PAIR_FILES[pair]
    feather = DATA_DIR / f"{pf}-5m.feather"
    if not feather.exists():
        return {}

    df = pd.read_feather(feather).rename(columns={"date": "open_time"})
    df = df.sort_values("open_time").reset_index(drop=True)

    # Find fold split point
    fold_end_raw = fold["fold_end"]
    fold_end = pd.to_datetime(fold_end_raw)
    if fold_end.tz is None:
        fold_end = fold_end.tz_localize("UTC")
    split_idx = df[df["open_time"] >= fold_end].index
    if len(split_idx) == 0:
        return {}
    si = split_idx[0]

    test_start = si
    test_end   = min(si + TEST_N, len(df))
    if test_end - test_start < 100:
        return {}

    test_df = df.iloc[test_start:test_end].copy()
    test_df = test_df.reset_index(drop=True)

    # Build features on test slice
    try:
        test_df = build_features(test_df)
    except Exception:
        return {}

    missing = [c for c in FEATURE_COLS if c not in test_df.columns]
    if missing:
        print(f"  WARN: missing {missing}")
        return {}

    feat_df = test_df[FEATURE_COLS].replace([np.inf, -np.inf], np.nan).fillna(0)
    model, scaler = load_pair(pair)
    if model is None or scaler is None:
        return {}

    try:
        probs = model.predict_proba(scaler.transform(feat_df.values))[:, 1]
    except Exception:
        return {}

    test_df["probability"] = probs

    if "label" not in test_df.columns or "atr14" not in test_df.columns:
        return {}

    HOLDING = 12   # candles = 1 hour (matches label's lookahead)

    results = {}
    for thresh in thresholds:
        trades, pnl_list = [], []
        outcome_list = []
        in_trade = False
        entry_atr = None
        entry_prob = None

        for i in range(len(test_df) - HOLDING):
            row = test_df.iloc[i]
            exit_row = test_df.iloc[i + HOLDING]

            if not in_trade:
                if row["probability"] >= thresh:
                    in_trade = True
                    entry_atr = row["atr14"]
                    entry_prob = row["probability"]
            else:
                # Win if ATR expands >= 5% over hold period (matches label definition)
                vol_expanded = 1 if (exit_row["atr14"] > entry_atr * 1.05) else 0
                net_pnl = 1.0 if vol_expanded else -1.0
                net_pnl -= 2 * FEE_PCT   # entry + exit fee drag

                trades.append({
                    "net_profit": net_pnl,
                    "is_win": net_pnl > 0,
                    "outcome": vol_expanded,
                    "probability": entry_prob,
                })
                pnl_list.append(net_pnl)
                outcome_list.append(vol_expanded)
                in_trade = False

        if trades:
            tdf = pd.DataFrame(trades)
            results[thresh] = {
                "trades": len(tdf),
                "wins": int(tdf["is_win"].sum()),
                "losses": int((~tdf["is_win"]).sum()),
                "net_profit": float(tdf["net_profit"].sum()),
                "expectancy": float(tdf["net_profit"].mean()),
                "pnl_list": pnl_list,
                "outcome_list": outcome_list,
                "vol_expansion_rate": float(tdf["outcome"].mean()),
            }
        else:
            results[thresh] = {
                "trades": 0, "wins": 0, "losses": 0,
                "net_profit": 0.0, "expectancy": 0.0,
                "pnl_list": [], "outcome_list": [],
                "vol_expansion_rate": 0.0,
            }
    return results

import pandas as pd
import numpy as np

def run():
    folds = load_folds()
    print(f"Folds: {len(folds)}  Pairs: {PAIRS}  Thresholds: {THRESHOLDS}")
    print()

    aggregated = {t: [] for t in THRESHOLDS}

    for pair in PAIRS:
        print(f"── {pair} ──")
        pair_fold_count = 0
        for fold in folds:
            res = replay_fold(pair, fold, THRESHOLDS)
            if res:
                for t in THRESHOLDS:
                    aggregated[t].extend(res[t]["pnl_list"])
                pair_fold_count += 1
            gc.collect()
        print(f"  {pair_fold_count} folds contributed")

    print("\n" + "=" * 70)
    print("E001b — GROUND-TRUTH REPLAY RESULTS")
    print("=" * 70)

    records = []
    for thresh in THRESHOLDS:
        pnls = np.array(aggregated[thresh])
        n = len(pnls)
        if n == 0:
            records.append({"threshold": thresh, "trades": 0, "wins": 0, "losses": 0,
                "win_rate_pct": 0, "avg_win": 0, "avg_loss": 0, "gross_profit": 0,
                "gross_loss": 0, "profit_factor": 0, "total_pnl": 0, "expectancy": 0,
                "max_drawdown": 0, "max_drawdown_pct": 0, "mfe_mean": 0, "mae_mean": 0,
                "median_trade": 0, "breakeven_win_rate": 0})
            continue

        wins  = int((pnls > 0).sum())
        loss  = n - wins
        tp    = float(pnls.sum())
        wr    = wins / n * 100
        aw    = float(pnls[pnls > 0].mean()) if wins > 0 else 0.0
        al    = abs(float(pnls[pnls <= 0].mean())) if loss > 0 else 0.0
        gp    = float(pnls[pnls > 0].sum())
        gl    = abs(float(pnls[pnls <= 0].sum()))
        pf    = gp / max(gl, 1e-9)
        exp   = tp / n
        cum   = np.cumsum(pnls)
        peak  = np.maximum.accumulate(cum)
        dd    = cum - peak
        max_dd = float(dd.min())
        max_dd_pct = abs(max_dd) / (np.maximum.accumulate(cum).max() + 1e-9) * 100
        be    = al / (aw + al) * 100 if (aw + al) > 0 else 0.0

        print(f"  {thresh:.2f}  n={n:5d}  WR={wr:.1f}%  PF={pf:.3f}  E={exp:+.5f}  DD={max_dd_pct:.1f}%")

        records.append({"threshold": thresh, "trades": n, "wins": wins, "losses": loss,
            "win_rate_pct": round(wr, 2), "avg_win": round(aw, 6), "avg_loss": round(al, 6),
            "gross_profit": round(gp, 4), "gross_loss": round(gl, 4),
            "profit_factor": round(pf, 3), "total_pnl": round(tp, 4),
            "expectancy": round(exp, 6), "max_drawdown": round(max_dd, 4),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "mfe_mean": 0, "mae_mean": 0, "median_trade": round(float(np.median(pnls)), 6),
            "breakeven_win_rate": round(be, 2)})

    df = pd.DataFrame(records)
    df, best, rec = rank_thresholds(df, primary_metric="expectancy")

    manifest = {
        "experiment_id": "E001b", "experiment": "E001b",
        "title": "Ground-Truth Threshold Replay",
        "hypothesis": "0.65 produces higher expectancy than 0.55 in ground-truth replay.",
        "null_hypothesis": "No difference in expectancy between 0.65 and 0.55.",
        "decision_metric": "expectancy",
        "secondary_metrics": ["profit_factor", "max_drawdown_pct", "trades", "win_rate_pct"],
        "status": "completed", "method": "full_candle_level_replay",
        "pairs": PAIRS, "model": "C (15 stable features) — v4.4",
        "folds_per_pair": len(folds), "fee_pct": FEE_PCT,
    }
    params = {
        "thresholds": str(THRESHOLDS), "model": "C (15 stable)",
        "pairs": ", ".join(PAIRS), "fee_pct": str(FEE_PCT),
        "method": "full_candle_level_replay",
        "folds_per_pair": str(len(folds)),
        "candles": f"{TRAIN_N}/{TEST_N}",
    }

    path = generate_html_report("E001b", "Ground-Truth Threshold Replay",
        manifest["hypothesis"], manifest["null_hypothesis"],
        params, df, best, rec, manifest, str(OUTPUT_DIR))
    print(f"\nReport: {path}")
    return df, best, rec


if __name__ == "__main__":
    run()
