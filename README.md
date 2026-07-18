# LeahAI Trading System

Custom Freqtrade strategy with XGBoost volatility-expansion classifier and a quantitative evaluation harness.

## Architecture

```
LeahAI.py              ← Main strategy (Freqtrade plugin)
├── LeahAIv4Classifier  ← XGBClassifier, 15-feature, per-pair models
├── FreqAI integration  ← Trains/loads FreqAI models alongside v4.4
└── v4.4 override        ← Shadow/paper mode: v4.4 probabilities gate entries

leah-eval/              ← Evaluation harness (walkforward + replay)
├── E001 threshold sweep   Entry threshold optimization
├── E001b ground-truth     Live-trade replay validation
├── E001c strategy replay  Strategy logic replay
├── E001d exit attribution Exit reason analysis
└── E002 expansion quality Label quality vs. trade outcomes
```

## Key Files

| File | Purpose |
|------|---------|
| `user_data/strategies/LeahAI.py` | Main strategy |
| `user_data/configs/config_lea.json` | Bot configuration |
| `leah-eval/` | Evaluation harness |
| `docs/ARCHITECTURE_CONSOLIDATION.md` | System design |
| `docs/v5-SPEC.md` | v5 specification |
| `retrain_15f_classifier.py` | Per-pair model retraining |

## Deployment History

| Version | Status |
|---------|--------|
| v4.4 | **Live** — paper trading (dry_run=true), `force_v44_model=true` |
| v5 | Spec complete, implementation pending |

## Current Mode

- **Paper trading** — dry_run=true, no real capital
- **v4.4 active** — XGBClassifier predicts volatility expansion probability; trades fire when prob > 0.55
- **FreqAI active** — Trains alongside v4.4, loaded for lookups

## Pairs

BTC/USDT, ETH/USDT, SOL/USDT, LINK/USDT (Contabo Docker, freqtrade-lea-new container)

## Setup

```bash
# Retrain per-pair models
python retrain_15f_classifier.py

# Run evaluation harness
cd leah-eval && python -m core.walkforward

# Check v4.4 prediction distributions
python parse_probwatch.py
```
