"""
Chronos Zero-Shot Directional Accuracy Test
Tests whether Amazon Chronos can predict BTC pair candle direction.

Measures: Does the median forecast predict actual next-candle direction?
Decision gate: >52-55% accuracy = signal exists, <=51% = noise
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path
import json
from datetime import datetime

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

DATA_DIR = Path("user_data/data/binance")
PAIRS = ["ALGO_BTC", "ATOM_BTC", "XRP_BTC", "LTC_BTC", "LINK_BTC"]
CONTEXT_LENGTH = 64       # candles of history to feed Chronos
PREDICTION_LENGTH = 1     # predict next candle
TEST_SIZE = 50            # number of out-of-sample tests per pair (reduced for CPU speed)


def load_pair_data(pair: str, timeframe: str = "5m") -> pd.DataFrame:
    """Load OHLCV feather file for a pair."""
    path = DATA_DIR / f"{pair}-{timeframe}.feather"
    if not path.exists():
        print(f"  WARNING: {path} not found, skipping")
        return pd.DataFrame()
    df = pd.read_feather(path)
    # Ensure sorted by date
    if "date" in df.columns:
        df = df.sort_values("date").reset_index(drop=True)
    return df


def run_chronos_test():
    """Run zero-shot directional accuracy test across all pairs."""
    import torch
    from chronos import ChronosPipeline

    print("=" * 60)
    print("CHRONOS ZERO-SHOT DIRECTIONAL ACCURACY TEST")
    print("=" * 60)
    print(f"Model: amazon/chronos-t5-mini")
    print(f"Context: {CONTEXT_LENGTH} candles")
    print(f"Test samples per pair: {TEST_SIZE}")
    print()

    # Load model
    print("Loading Chronos model...")
    pipeline = ChronosPipeline.from_pretrained(
        "amazon/chronos-t5-mini",
        device_map="auto",
        dtype=torch.float32,
    )
    print("Model loaded.\n")

    results = {}

    for pair in PAIRS:
        print(f"Testing {pair}...")
        df = load_pair_data(pair, "5m")
        if df.empty or len(df) < CONTEXT_LENGTH + TEST_SIZE + 10:
            print(f"  Not enough data ({len(df)} rows), skipping")
            continue

        close = df["close"].values.astype(np.float64)

        correct = 0
        total = 0
        predictions_detail = []

        # Walk-forward test
        for i in range(len(close) - TEST_SIZE - 1, len(close) - 1):
            context = close[i - CONTEXT_LENGTH:i]
            actual_next = close[i]
            actual_direction = 1 if actual_next > close[i - 1] else 0

            # Chronos prediction
            context_tensor = torch.tensor(context).unsqueeze(0)
            forecast = pipeline.predict(
                context_tensor,
                prediction_length=PREDICTION_LENGTH,
                num_samples=10,
            )
            # forecast shape: (1, num_samples, prediction_length)
            median_pred = np.median(forecast[0].numpy())

            pred_direction = 1 if median_pred > close[i - 1] else 0
            is_correct = pred_direction == actual_direction

            if is_correct:
                correct += 1
            total += 1

            predictions_detail.append({
                "idx": i,
                "actual": actual_next,
                "predicted": median_pred,
                "actual_dir": actual_direction,
                "pred_dir": pred_direction,
                "correct": is_correct,
            })

        accuracy = correct / total * 100 if total > 0 else 0
        results[pair] = {
            "accuracy": accuracy,
            "correct": correct,
            "total": total,
        }
        print(f"  {pair}: {accuracy:.1f}% ({correct}/{total})")

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    all_correct = sum(r["correct"] for r in results.values())
    all_total = sum(r["total"] for r in results.values())
    overall_acc = all_correct / all_total * 100 if all_total > 0 else 0

    for pair, r in sorted(results.items(), key=lambda x: x[1]["accuracy"], reverse=True):
        verdict = "SIGNAL" if r["accuracy"] > 52 else "NOISE"
        print(f"  {pair:12s} | {r['accuracy']:5.1f}% ({r['correct']}/{r['total']}) | {verdict}")

    print(f"\n  OVERALL: {overall_acc:.1f}% ({all_correct}/{all_total})")

    if overall_acc > 55:
        print("\n  VERDICT: STRONG SIGNAL - fine-tuning warranted")
    elif overall_acc > 52:
        print("\n  VERDICT: WEAK SIGNAL - fine-tuning may help")
    else:
        print("\n  VERDICT: NOISE - Chronos has no directional power on BTC pairs")

    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "model": "amazon/chronos-t5-mini",
        "context_length": CONTEXT_LENGTH,
        "test_size": TEST_SIZE,
        "results": results,
        "overall_accuracy": overall_acc,
        "overall_correct": all_correct,
        "overall_total": all_total,
    }
    with open("chronos_test_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to chronos_test_results.json")


if __name__ == "__main__":
    run_chronos_test()
