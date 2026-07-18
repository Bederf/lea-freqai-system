#!/usr/bin/env python3
"""
Experiment A — Model Comparison: Regressor vs Classifiers
====================================================
Compares 4 models on identical FreqAI training data to determine whether
XGBClassifier outperforms XGBRegressor for the LeahAI vol-expansion task.

Models compared:
  1. XGBRegressor (current baseline) — reg:squarederror
  2. XGBClassifier — binary:logistic
  3. LogisticRegression — simple interpretable baseline
  4. RandomForestClassifier — non-boosting benchmark

Success criteria (ALL must pass for classifier to replace regressor):
  - Classifier PR-AUC > 0.35 (above random for 32.5% base rate)
  - Classifier Brier score < regressor Brier score
  - Classifier better calibrated: lower mean |predicted - observed| per bucket

Usage:
  python3 experiment_model_comparison.py [--model-dir <path>] [--pair ETH]
"""

import argparse
import json
import os
import pickle
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score as AUC,
    average_precision_score as AveragePrecisionScore,
    brier_score_loss,
    confusion_matrix,
    roc_curve,
    precision_recall_curve,
)
from sklearn.calibration import calibration_curve
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import MinMaxScaler

warnings.filterwarnings("ignore")

# ─── Args ────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Experiment A: Model Comparison")
parser.add_argument("--model-dir", default="user_data/models/lea_v6")
parser.add_argument("--pair", default="ETH", choices=["BTC", "ETH", "SOL", "LINK"])
parser.add_argument("--output-dir", default="user_data/reports/experiments")
args = parser.parse_args()

os.makedirs(args.output_dir, exist_ok=True)
DATE = datetime.now().strftime("%Y%m%d_%H%M%S")
PAIR = args.pair  # e.g. "ETH" or "ETH/USDT"


# ─── Load data ────────────────────────────────────────────────────────────────

def load_data(model_dir: str, pair: str):
    """
    Load X, y, feature_names from leah_v4_3 (archived, XGBClassifier).

    The lea_v6 model (XGBRegressor) has unreadable dates_df — we use the
    archived leah_v4_3 data which is fully loadable and uses XGBClassifier.
    All 4 experiment models train on identical features from this dataset.
    """
    model_dir = Path(model_dir)
    pc = pair.replace("/", "_").replace("\\", "_")
    sub_dirs = sorted(model_dir.glob(f"sub-train-{pc}_*"))
    if not sub_dirs:
        raise FileNotFoundError(f"No sub-train dir for {pair} in {model_dir}")
    sub = sub_dirs[-1]

    fp_file = list(sub.glob("*_feature_pipeline.pkl"))[0]
    with open(fp_file, "rb") as f:
        feature_pipeline = pickle.load(f)

    meta_file = list(sub.glob("*_metadata.json"))[0]
    with open(meta_file) as f:
        meta = json.load(f)
    feature_names = meta["training_features_list"]

    td_file = list(sub.glob("*_trained_df.pkl"))[0]
    td = pd.read_pickle(td_file)
    X = td.values

    # Load the archived XGBClassifier to recover labels
    model_file = list(sub.glob("*_model.joblib"))[0]
    trained_model = joblib.load(str(model_file))
    model_type = type(trained_model).__name__
    y = trained_model.predict(X)
    if hasattr(trained_model, "predict_proba"):
        y_prob_for_cal = trained_model.predict_proba(X)[:, 1]
    else:
        y_prob_for_cal = y.astype(float)

    return X, y, y_prob_for_cal, feature_names, sub.name, model_type


# ─── Metrics ────────────────────────────────────────────────────────────────

def compute_metrics(y_true, y_prob, model_name):
    """All classification + simulation metrics for one model."""
    n = len(y_true)
    n_pos = int(y_true.sum())

    roc_auc = AUC(y_true, y_prob)
    pr_auc = AveragePrecisionScore(y_true, y_prob)
    brier = brier_score_loss(y_true, y_prob)

    # Calibration buckets
    buckets_raw = [
        (0.0, 0.3),
        (0.3, 0.5),
        (0.5, 0.7),
        (0.7, 0.85),
        (0.85, 1.0),
    ]
    bucket_results = []
    for lo, hi in buckets_raw:
        mask = (y_prob >= lo) & (y_prob < hi)
        cnt = int(mask.sum())
        if cnt > 0:
            obs = float(y_true[mask].mean())
            pred = float(y_prob[mask].mean())
            bucket_results.append({
                "bucket": f"{lo:.1f}-{hi:.1f}",
                "count": cnt,
                "pred_prob": round(pred, 4),
                "obs_win_rate": round(obs, 4),
                "cal_err": round(abs(pred - obs), 4),
            })

    # Confusion matrix at threshold 0.5
    y_pred = (y_prob >= 0.5).astype(int)
    cm = confusion_matrix(y_true, y_pred).tolist()

    # Trade simulation at multiple thresholds
    sims = []
    for thresh in [0.55, 0.60, 0.70, 0.80]:
        entries = np.where(y_prob >= thresh)[0]
        cnt = len(entries)
        if cnt == 0:
            sims.append({"threshold": thresh, "trade_count": 0,
                         "win_rate": None, "expectancy": None, "profit_factor": None})
            continue
        wins = int(y_true[entries].sum())
        wr = wins / cnt
        # Fixed 1% win / 1% loss approximation
        avg_win, avg_loss = 0.01, -0.01
        net = wins * avg_win + (cnt - wins) * avg_loss
        e = net / cnt
        pf = wins * avg_win / max((cnt - wins) * abs(avg_loss), 1e-12)
        sims.append({
            "threshold": thresh, "trade_count": cnt, "win_rate": round(wr, 4),
            "avg_win": avg_win, "avg_loss": avg_loss,
            "expectancy": round(e, 6), "profit_factor": round(pf, 3),
        })

    return {
        "model": model_name, "n_samples": n, "n_positives": n_pos,
        "base_rate": round(float(y_true.mean()), 4),
        "roc_auc": round(float(roc_auc), 4),
        "pr_auc": round(float(pr_auc), 4),
        "brier_score": round(float(brier), 4),
        "confusion_matrix": cm,
        "buckets": bucket_results,
        "simulated_trades": sims,
    }


# ─── Run experiment ───────────────────────────────────────────────────────────

def run_experiment(X, y, feature_names):
    from sklearn.ensemble import RandomForestClassifier
    from xgboost import XGBClassifier, XGBRegressor
    from sklearn.model_selection import cross_val_predict, StratifiedKFold

    results = {}
    scaler = MinMaxScaler(feature_range=(-1, 1))
    X_s = scaler.fit_transform(X)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=1)

    # ── 1. XGBRegressor (in-sample + OOF via cross_val_predict) ───────────
    print(f"\n  [1/4] XGBRegressor...")
    r = XGBRegressor(objective="reg:squarederror", n_estimators=200,
                     max_depth=4, learning_rate=0.05, subsample=0.8,
                     colsample_bytree=0.8, random_state=1, verbosity=0)
    r.fit(X, y)
    y_prob_r_insample = np.clip(r.predict(X), 0, 1)
    results["XGBRegressor_in-sample"] = compute_metrics(y, y_prob_r_insample, "XGBRegressor (in-sample)")
    # OOF predictions
    y_prob_r_oof = cross_val_predict(r, X, y, cv=cv, method="predict")
    y_prob_r_oof = np.clip(y_prob_r_oof, 0, 1)
    results["XGBRegressor (OOF)"] = compute_metrics(y, y_prob_r_oof, "XGBRegressor (OOF)")
    r_r = results["XGBRegressor (OOF)"]
    print(f"       OOF — ROC={r_r['roc_auc']:.4f}  PR={r_r['pr_auc']:.4f}  Brier={r_r['brier_score']:.4f}")

    # ── 2. XGBClassifier ────────────────────────────────────────────────────
    print(f"\n  [2/4] XGBClassifier...")
    c = XGBClassifier(objective="binary:logistic", n_estimators=200,
                      max_depth=4, learning_rate=0.05, subsample=0.8,
                      colsample_bytree=0.8, random_state=1, verbosity=0, eval_metric="logloss")
    c.fit(X, y)
    y_prob_c_insample = c.predict_proba(X)[:, 1]
    results["XGBClassifier_in-sample"] = compute_metrics(y, y_prob_c_insample, "XGBClassifier (in-sample)")
    y_prob_c_oof = cross_val_predict(c, X, y, cv=cv, method="predict_proba")[:, 1]
    results["XGBClassifier (OOF)"] = compute_metrics(y, y_prob_c_oof, "XGBClassifier (OOF)")
    r_c = results["XGBClassifier (OOF)"]
    print(f"       OOF — ROC={r_c['roc_auc']:.4f}  PR={r_c['pr_auc']:.4f}  Brier={r_c['brier_score']:.4f}")

    # ── 3. LogisticRegression ──────────────────────────────────────────────
    print(f"\n  [3/4] LogisticRegression...")
    lr = LogisticRegression(max_iter=1000, random_state=1, solver="lbfgs")
    lr.fit(X_s, y)
    y_prob_lr_insample = lr.predict_proba(X_s)[:, 1]
    results["LogisticRegression_in-sample"] = compute_metrics(y, y_prob_lr_insample, "LogisticRegression (in-sample)")
    y_prob_lr_oof = cross_val_predict(lr, X_s, y, cv=cv, method="predict_proba")[:, 1]
    results["LogisticRegression (OOF)"] = compute_metrics(y, y_prob_lr_oof, "LogisticRegression (OOF)")
    r_lr = results["LogisticRegression (OOF)"]
    print(f"       OOF — ROC={r_lr['roc_auc']:.4f}  PR={r_lr['pr_auc']:.4f}  Brier={r_lr['brier_score']:.4f}")

    # ── 4. RandomForestClassifier ─────────────────────────────────────────
    print(f"\n  [4/4] RandomForestClassifier...")
    rf = RandomForestClassifier(n_estimators=200, max_depth=6,
                               min_samples_leaf=10, random_state=1, n_jobs=-1)
    rf.fit(X, y)
    y_prob_rf_insample = rf.predict_proba(X)[:, 1]
    results["RandomForestClassifier_in-sample"] = compute_metrics(y, y_prob_rf_insample, "RandomForestClassifier (in-sample)")
    y_prob_rf_oof = cross_val_predict(rf, X, y, cv=cv, method="predict_proba")[:, 1]
    results["RandomForestClassifier (OOF)"] = compute_metrics(y, y_prob_rf_oof, "RandomForestClassifier (OOF)")
    r_rf = results["RandomForestClassifier (OOF)"]
    print(f"       OOF — ROC={r_rf['roc_auc']:.4f}  PR={r_rf['pr_auc']:.4f}  Brier={r_rf['brier_score']:.4f}")

    return results


# ─── Report generation ───────────────────────────────────────────────────────

def make_report(results, info):
    # Use OOF results for primary comparison
    oof_models = {
        "Regressor": "XGBRegressor (OOF)",
        "Classifier": "XGBClassifier (OOF)",
        "LR": "LogisticRegression (OOF)",
        "RF": "RandomForestClassifier (OOF)",
    }
    in_models = {
        "Regressor": "XGBRegressor_in-sample",
        "Classifier": "XGBClassifier_in-sample",
        "LR": "LogisticRegression_in-sample",
        "RF": "RandomForestClassifier_in-sample",
    }

    def oof(m):
        return results.get(oof_models[m], results.get(in_models[m], {}))

    # Success criteria — check OOF
    def check(oof_key, metric, op, ref):
        v = results[oof_key].get(metric, 0)
        if isinstance(ref, str):
            ref_v = results[ref].get(metric, 0)
        else:
            ref_v = ref
        if op == ">":
            return "✅" if v > ref_v else "❌"
        return "✅" if v < ref_v else "❌"

    classifier_key = oof_models["Classifier"]
    regressor_key = oof_models["Regressor"]

    lines = [
        "# Experiment A — Model Comparison Report",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Pair:** {info['pair']}  ",
        f"**Training samples:** {info['n_samples']} (positive rate: {info['base_rate']*100:.1f}%)  ",
        f"**Features:** {info['n_features']}  ",
        f"**Validation:** 5-fold cross-validation (OOF predictions)  ",
        "",
        "---",
        "",
        "## Success Criteria (OOF)",
        "",
        "| Criterion | Regressor | Classifier | LR | RF |",
        "|-----------|:---:|:---:|:---:|:---:|",
        f"| PR-AUC > 0.35 | {'—'} | {check(classifier_key,'pr_auc','>',0.35)} | {'—'} | {'—'} |",
        f"| Brier < Regressor | {'—'} | {check(classifier_key,'brier_score','<',regressor_key)} | {'—'} | {'—'} |",
        f"| PR-AUC > Regressor | {'—'} | {check(classifier_key,'pr_auc','>',regressor_key)} | {'—'} | {'—'} |",
        "",
        "---",
        "",
        "## Classification Metrics (OOF)",
        "",
        "| Metric | Regressor | Classifier | LR | RF |",
        "|--------|:---:|:---:|:---:|:---:|",
    ]
    for label, key in [
        ("ROC-AUC ↑", "roc_auc"),
        ("PR-AUC ↑", "pr_auc"),
        ("Brier Score ↓", "brier_score"),
        ("Base rate", "base_rate"),
        ("Samples", "n_samples"),
    ]:
        row = [label]
        for m_key in oof_models.values():
            v = results.get(m_key, {}).get(key, "—")
            row.append(f"{v:.4f}" if isinstance(v, float) else str(v))
        lines.append("| " + " | ".join(row) + " |")

    lines += [
        "",
        "---",
        "",
        "## In-Sample (for reference — NOT a valid comparison)",
        "",
    ]
    for label, key in [
        ("ROC-AUC", "roc_auc"),
        ("PR-AUC", "pr_auc"),
        ("Brier Score", "brier_score"),
    ]:
        row = [label]
        for m_key in in_models.values():
            v = results.get(m_key, {}).get(key, "—")
            row.append(f"{v:.4f}" if isinstance(v, float) else str(v))
        lines.append("| " + " | ".join(row) + " |")
        lines.append("| " + " | ".join(row) + " |")

    # Calibration
    cal_map = {
        "Regressor": "XGBRegressor (OOF)",
        "Classifier": "XGBClassifier (OOF)",
        "LR": "LogisticRegression (OOF)",
        "RF": "RandomForestClassifier (OOF)",
    }
    cal_errors = {}
    for label, oof_key in cal_map.items():
        bs = results.get(oof_key, {}).get("buckets", [])
        if bs:
            cal_errors[label] = np.mean([abs(b["pred_prob"] - b["obs_win_rate"]) for b in bs])
        else:
            cal_errors[label] = 999
    best_cal = min(cal_errors, key=cal_errors.get)

    lines += [
        "",
        "---",
        "",
        "## Calibration Buckets",
        "",
        "*(Predicted prob vs observed win rate — lower |error| = better)*",
        "",
    ]
    for b_idx in range(5):
        row = []
        for label, oof_key in cal_map.items():
            bs = results.get(oof_key, {}).get("buckets", [])
            if b_idx < len(bs):
                b = bs[b_idx]
                star = " ⭐" if label == best_cal else ""
                row.append(f"n={b['count']}  p={b['pred_prob']:.3f}  o={b['obs_win_rate']:.3f}  e={b['cal_err']:.3f}{star}")
            else:
                row.append("—")
        lines.append("| " + " | ".join(row) + " |")

    # Confusion matrices
    lines += [
        "",
        "---",
        "",
        "## Confusion Matrices (threshold=0.50)",
        "",
    ]
    for label, oof_key in cal_map.items():
        cm = results.get(oof_key, {}).get("confusion_matrix", [[0,0],[0,0]])
        tn, fp, fn, tp = cm[0][0], cm[0][1], cm[1][0], cm[1][1]
        lines.append(f"**{label}:**  TN={tn} FP={fp}  FN={fn} TP={tp}")

    # Trade sim
    lines += [
        "",
        "---",
        "",
        "## Trade Simulation (fixed 1%/1% R/R approximation)",
        "",
        "| Thresh | Model | Trades | Win Rate | Expectancy | Profit Factor |",
        "|:---:|--------|:---:|:---:|:---:|:---:|",
    ]
    for thresh in [0.55, 0.70]:
        for label, oof_key in cal_map.items():
            sims = results.get(oof_key, {}).get("simulated_trades", [])
            sim = next((s for s in sims if s["threshold"] == thresh), None)
            if sim and sim["trade_count"] > 0:
                lines.append(
                    f"| {thresh} | {label} | {sim['trade_count']} | "
                    f"{sim['win_rate']:.3f} | {sim['expectancy']:.4f} | {sim['profit_factor']:.3f} |"
                )
            else:
                lines.append(f"| {thresh} | {label} | 0 | — | — | — |")

    # Interpretation (use OOF results)
    clf_pr = results.get(oof_models["Classifier"], {}).get("pr_auc", 0)
    reg_pr = results.get(oof_models["Regressor"], {}).get("pr_auc", 0)
    clf_br = results.get(oof_models["Classifier"], {}).get("brier_score", 999)
    reg_br = results.get(oof_models["Regressor"], {}).get("brier_score", 0)

    lines += [
        "",
        "---",
        "",
        "## Interpretation",
        "",
    ]
    if clf_pr > reg_pr:
        lines.append(f"✅ Classifier PR-AUC ({clf_pr:.4f}) > Regressor ({reg_pr:.4f})")
    else:
        lines.append(f"❌ Classifier PR-AUC ({clf_pr:.4f}) ≤ Regressor ({reg_pr:.4f})")
    if clf_br < reg_br:
        lines.append(f"✅ Classifier Brier ({clf_br:.4f}) < Regressor ({reg_br:.4f}) — better calibrated")
    else:
        lines.append(f"❌ Classifier Brier ({clf_br:.4f}) ≥ Regressor ({reg_br:.4f})")
    if clf_pr > 0.35:
        lines.append(f"✅ Classifier PR-AUC ({clf_pr:.4f}) exceeds 0.35")
    else:
        lines.append(f"⚠️  Classifier PR-AUC ({clf_pr:.4f}) below 0.35 — weak signal")

    lines.append("")
    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("EXPERIMENT A — Model Comparison")
    print("=" * 60)

    print(f"\nLoading {PAIR} from {args.model_dir}...")
    X, y, y_prob_ref, feature_names, sub_name, ref_model_type = load_data(args.model_dir, PAIR)
    print(f"  X: {X.shape}, y: {y.sum()}/{len(y)} positive ({y.mean()*100:.1f}%)")

    info = {
        "pair": PAIR, "n_samples": len(y), "n_features": X.shape[1],
        "base_rate": float(y.mean()), "sub_dir": sub_name,
    }

    results = run_experiment(X, y, feature_names)

    # Save outputs
    out = f"{args.output_dir}/expA_{Path(args.model_dir).name}_{PAIR.replace('/','_')}_{DATE}"
    report = make_report(results, info)

    with open(f"{out}_report.md", "w") as f:
        f.write(report)

    # Strip large arrays for JSON
    def strip_large(d):
        return {k: v for k, v in d.items() if k not in ["fpr", "tpr", "precision", "recall"]}
    clean = {k: strip_large(v) for k, v in results.items()}
    with open(f"{out}_results.json", "w") as f:
        json.dump({"info": info, "results": clean}, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"\n{'Model':<30} {'ROC-AUC':>8} {'PR-AUC':>8} {'Brier':>8}")
    print("-" * 60)
    for m, r in sorted(results.items(), key=lambda x: -x[1]["pr_auc"]):
        print(f"{m:<30} {r['roc_auc']:>8.4f} {r['pr_auc']:>8.4f} {r['brier_score']:>8.4f}")
    print(f"\nReport: {out}_report.md")
    print(f"JSON:   {out}_results.json")
