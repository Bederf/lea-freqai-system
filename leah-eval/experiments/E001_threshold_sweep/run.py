"""
E001 — Probability Threshold Sweep
====================================
Leah Evaluation Harness, Experiment 001

HYPOTHESIS: Lowering the entry probability threshold from 0.55 to 0.50
(or nearby) increases expectancy while maintaining acceptable drawdown.

NULL HYPOTHESIS: No improvement in expectancy when threshold is changed.

DECISION METRIC: expectancy
SECONDARY: profit_factor, max_drawdown_pct, trades, win_rate_pct

Uses walk-forward fold aggregate statistics for fast approximation.
Ground truth requires full candle-level replay (TODO: E001b).
"""

import sys
import csv
from pathlib import Path

# Add project root to path
# run.py is at: leah-eval/experiments/E001_threshold_sweep/run.py
# PROJECT_ROOT = leah-eval/../../../ = /home/shad/lea-freqai-system
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

# Handle package vs filesystem import
try:
    from leah_eval.core.metrics import compute_threshold_sweep, rank_thresholds
    from leah_eval.core.reporting import generate_html_report
except ModuleNotFoundError:
    # Fallback: direct import from core files
    import importlib.util
    def load_module(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    metrics_mod = load_module("metrics", PROJECT_ROOT / "leah-eval" / "core" / "metrics.py")
    reporting_mod = load_module("reporting", PROJECT_ROOT / "leah-eval" / "core" / "reporting.py")
    rank_thresholds = metrics_mod.rank_thresholds
    generate_html_report = reporting_mod.generate_html_report


# ─── Configuration ─────────────────────────────────────────────────────────────

THRESHOLDS = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
PAIRS = ["BTC", "ETH", "SOL", "LINK"]
FEE_PCT = 0.002  # round-trip fees

# Path to the pre-computed fold results from experiment E
FOLD_DATA_PATH = Path(
    "/home/shad/lea-freqai-system/user_data/reports/experiments/expE_BTC_20260711_211246.csv"
)
OUTPUT_DIR = Path(__file__).parent.parent.parent / "reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ─── Load fold results per model ───────────────────────────────────────────────

def load_fold_results(path: Path) -> dict[str, list[dict]]:
    """Load fold results, grouped by model label."""
    by_model = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            model = row["model"]
            if model not in by_model:
                by_model[model] = []
            by_model[model].append({
                "model": model,
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
    return by_model


def approximate_sweep(
    prob_means: list[float],
    prob_stds: list[float],
    test_ns: list[int],
    positive_rates: list[float],
    thresholds: list[float],
    fee_pct: float = 0.002,
) -> pd.DataFrame:
    """
    Fast threshold sweep using normal approximation of the P(E) distribution.

    For each threshold, estimate trade count from the probability distribution
    and derive approximate win rate from the base positive rate conditioned on
    passing the threshold.

    This is a fast approximation. Full candle-level replay is the ground truth.
    """
    import math

    def norm_cdf(x):
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    records = []

    for thresh in thresholds:
        total_trades = 0
        total_wins = 0
        all_pnls = []

        for mu, sigma, n, pos_rate in zip(prob_means, prob_stds, test_ns, positive_rates):
            if sigma <= 0:
                continue

            z = (thresh - mu) / sigma
            p_pass = 1 - norm_cdf(z)  # fraction of candles passing threshold
            n_trades = max(int(n * p_pass), 0)

            if n_trades == 0:
                continue

            # Estimate win rate: P(win | P >= thresh)
            # Use conditional probability approximation:
            # P(win | P >= thresh) ≈ E[positive_rate | P >= thresh]
            # Approximated by: base positive_rate * (1 + alpha * z) clamped to [0.3, 0.95]
            # alpha captures how probability correlates with outcome
            alpha = 0.35  # calibrated from training set calibration analysis
            cond_win_rate = pos_rate * (1 + alpha * max(z, -0.5))
            cond_win_rate = max(0.25, min(0.95, cond_win_rate))

            n_wins = int(round(n_trades * cond_win_rate))
            n_losses = n_trades - n_wins

            gross_win = 1 - fee_pct       # +0.998 per unit
            gross_loss = -(1 + fee_pct)    # -1.002 per unit

            trade_pnl = n_wins * gross_win + n_losses * gross_loss

            total_trades += n_trades
            total_wins += n_wins
            for _ in range(n_wins):
                all_pnls.append(gross_win)
            for _ in range(n_losses):
                all_pnls.append(gross_loss)

        if total_trades == 0:
            records.append({
                "threshold": thresh, "trades": 0, "wins": 0, "losses": 0,
                "win_rate_pct": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "gross_profit": 0.0, "gross_loss": 0.0,
                "profit_factor": 0.0, "total_pnl": 0.0, "expectancy": 0.0,
                "max_drawdown": 0.0, "max_drawdown_pct": 0.0,
                "mfe_mean": 0.0, "mae_mean": 0.0,
                "median_trade": 0.0, "breakeven_win_rate": 0.0,
            })
            continue

        # Running P&L for drawdown
        all_pnls = np.array(all_pnls)
        cum = np.cumsum(all_pnls)
        peak = np.maximum.accumulate(cum)
        dd = cum - peak
        max_dd = dd.min()
        max_dd_pct = abs(max_dd) / (np.maximum.accumulate(cum).max() + 1e-9) * 100

        win_rate = total_wins / total_trades * 100
        avg_win_pnl = gross_win       # +0.998
        avg_loss_pnl = abs(gross_loss)  # +1.002 (absolute value)
        gross_profit_total = total_wins * avg_win_pnl
        gross_loss_total = (total_trades - total_wins) * avg_loss_pnl
        pf = gross_profit_total / max(gross_loss_total, 1e-9)
        total_pnl = gross_profit_total - gross_loss_total
        expectancy = total_pnl / total_trades

        records.append({
            "threshold": thresh,
            "trades": total_trades,
            "wins": total_wins,
            "losses": total_trades - total_wins,
            "win_rate_pct": round(win_rate, 2),
            "avg_win": round(avg_win_pnl, 6),
            "avg_loss": round(avg_loss_pnl, 6),
            "gross_profit": round(gross_profit_total, 4),
            "gross_loss": round(gross_loss_total, 4),
            "profit_factor": round(pf, 3),
            "total_pnl": round(total_pnl, 4),
            "expectancy": round(expectancy, 6),
            "max_drawdown": round(max_dd, 4),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "mfe_mean": 0.0,
            "mae_mean": 0.0,
            "median_trade": round(float(np.median(all_pnls)), 4),
            "breakeven_win_rate": round(avg_loss_pnl / (avg_win_pnl + avg_loss_pnl) * 100, 2),
        })

    return pd.DataFrame(records)


def run():
    print("=" * 70)
    print("E001 — Probability Threshold Sweep")
    print("=" * 70)

    by_model = load_fold_results(FOLD_DATA_PATH)

    # Focus on Model C (15 stable features = v4.4)
    model_c = by_model.get("C (15 stable)", [])
    if not model_c:
        print("ERROR: Model C fold results not found.")
        return

    print(f"\nModel C (15 stable features) — {len(model_c)} folds")
    print(f"Thresholds: {THRESHOLDS}")
    print(f"Pairs: {PAIRS}")

    # Aggregate across all folds
    prob_means = [f["prob_mean"] for f in model_c]
    prob_stds = [f["prob_std"] for f in model_c]
    test_ns = [f["test_n"] for f in model_c]
    positive_rates = [f["test_positive_rate"] for f in model_c]

    print(f"\nFold P(E) means: {[f'{m:.3f}' for m in prob_means[:5]]} ... ({len(prob_means)} total)")
    print(f"Fold P(E) stds:  {[f'{s:.3f}' for s in prob_stds[:5]]} ... ({len(prob_stds)} total)")

    # Run sweep
    results = approximate_sweep(
        prob_means, prob_stds, test_ns, positive_rates,
        THRESHOLDS, FEE_PCT,
    )

    # Rank and recommend
    results, best_row, recommendation = rank_thresholds(
        results, primary_metric="expectancy"
    )

    print("\n" + "=" * 70)
    print("RESULTS — Model C (15 stable features)")
    print("=" * 70)
    print(results[["threshold", "trades", "wins", "win_rate_pct", "profit_factor", "expectancy", "max_drawdown_pct"]].to_string(index=False))
    print()
    print(f"RECOMMENDATION: {recommendation}")

    # Save
    manifest = {
        "experiment_id": "E001",
        "experiment": "E001",
        "title": "Probability Threshold Sweep",
        "hypothesis": "Lowering the entry probability threshold from 0.55 to 0.50 (or nearby) increases expectancy.",
        "null_hypothesis": "No improvement in expectancy when threshold is changed.",
        "decision_metric": "expectancy",
        "secondary_metrics": ["profit_factor", "max_drawdown_pct", "trades", "win_rate_pct"],
        "status": "completed",
        "pairs": PAIRS,
        "model": "C (15 stable)",
        "folds": len(model_c),
        "fee_pct": FEE_PCT,
    }

    params = {
        "thresholds": str(THRESHOLDS),
        "model": "C (15 stable features)",
        "pairs": ", ".join(PAIRS),
        "fee_pct": str(FEE_PCT),
        "method": "normal_approximation_from_fold_stats",
        "folds_used": str(len(model_c)),
    }

    report_path = generate_html_report(
        experiment_id="E001",
        experiment_title="Probability Threshold Sweep",
        hypothesis=manifest["hypothesis"],
        null_hypothesis=manifest["null_hypothesis"],
        params=params,
        results_df=results,
        best_row=best_row,
        recommendation=recommendation,
        manifest=manifest,
        output_dir=str(OUTPUT_DIR),
    )

    print(f"\nReport saved: {report_path}")

    return results, best_row, recommendation


if __name__ == "__main__":
    run()
