# Paper Trading Validation Plan — LeahAI v4.4

**Date:** 2026-07-17
**Updated:** 2026-07-17
**Strategy:** LeahAI v6.1 (`user_data/strategies/LeahAI.py`)
**Config:** `dry_run=true`, `force_v44_model=true`
**Model:** LeahAI v4.4 — XGBClassifier, 15 features, vol expansion label
**Container:** `freqtrade-lea-new`

---

## Overview

LeahAI v4.4 is a **15-feature XGBClassifier** that predicts whether volatility will expand over the next 12 candles (ATR[i+12] > ATR[i] × 1.05). It is deployed inside the `freqtrade-lea-new` Docker container and overrides FreqAI's native regression output using the `force_v44_model=true` config flag.

The paper trading run validates v4.4's real-world signal quality before any capital is deployed.

---

## Pre-Paper Checklist

### Configuration ✅
- [x] Strategy deployed: `LeahAI` (LeahAIV5Strategy class)
- [x] v4.4 models trained and deployed (BTC, ETH, SOL, LINK)
- [x] `force_v44_model=true` — v4.4 is sole decision authority
- [x] `dry_run=true` — no real capital
- [x] Model files in container: `leah_v4_4_{PAIR}_xgb_clf.pkl` + `_scaler.pkl`
- [x] Snapshot logging re-enabled (bug fix applied 2026-07-17)

### Bugs Fixed (2026-07-17)
- [x] `custom_stake_amount` now reads `&-target` (v4.4 probability) not `"1"` (FreqAI column)
- [x] `_write_snapshot` now writes to `/freqtrade/user_data/logs/` (container path) not host bind-mount

### Safety Measures ✅
- [x] Max open trades: 3 (config)
- [x] Entry gate: prob > 0.55 + btc_trend + ema50 + volume + atr_pct_rank ≥ 80
- [x] Snapshot logging: every entry and exit written to `trade_snapshots_v6.jsonl`
- [x] No exit signals (`populate_exit_trend` → `exit_long=0`)
- [x] ROI table: {0: 5%, 30: 3%, 60: 2%, 120: 1%}
- [x] Time exit: underwater > 6h → force close

---

## Paper Trading Stages (Trust Ladder)

| Stage | Trades Required | Gate | Status |
|-------|---------------|------|--------|
| L1 | 10 v4.4 trades | Snapshot logging verified | ⬜ Pending |
| L2 | 25 v4.4 trades | Distribution within ±5pp of training band | ⬜ Pending |
| L3 | 50 v4.4 trades | Breakeven or better | ⬜ Pending |

---

## Distribution Monitoring

**Training bands (2026-07-11):**

| Pair | Mean | %>55 |
|------|------|------|
| BTC | 0.32 | 3% |
| ETH | 0.32 | 3% |
| SOL | 0.32 | 1% |
| LINK | 0.31 | 2% |

**L2 gate:** Each pair's live mean within ±5pp of training mean, and %>55 within ±5pp of training %>55.

**Cron:** `probwatch_v6` runs every 5 minutes and checks all 4 pairs. Alerts fire if any pair exits its L2 band.

---

## Current State

| ID | Pair | Date | Enter Tag | Prob | Status |
|---|---|---|---|---|---|
| 7–15 | various | Jul 10–15 | — | — | Closed (legacy FreqAI) |
| 16 | LINK/USDT | Jul 17 11:45 | prob_0.6739 | 0.6739 | Open — v4.4 ✅ |

**v4.4 paper trades:** 1 (Trade #16)
**Legacy trades:** 9 (not attributable to v4.4)

---

## Snapshot Format

Each entry/exit writes one JSON line to `trade_snapshots_v6.jsonl`:

```json
{
  "event": "entry",
  "ts": "2026-07-17T11:45:09Z",
  "pair": "LINK/USDT",
  "trade_id": 16,
  "strategy_name": "LeahAI",
  "strategy_version": "6.1",
  "v44_model": "leah_v4_4_xgb_clf",
  "v44_features": "15-feature vol expansion schema",
  "v44_override": true,
  "model_output": 0.6739,
  "g1_passed": true,
  "g2_passed": true,
  "g3_passed": true,
  "open_rate": 8.209,
  "enter_tag": "prob_0.6739"
}
```

---

## Next Steps

1. **Restart container** to load bug-fixed strategy (done 15:44 UTC)
2. **Wait for next v4.4 entry** — snapshot should fire and appear in `trade_snapshots_v6.jsonl`
3. **Verify snapshot** — confirm entry snapshot written to container log path
4. **L1 gate** — 10 v4.4 trades with valid snapshots
5. **L2 gate** — distribution check across 25 trades
6. **L3 gate** — 50 trades, breakeven or better → capital deployment review

---

## Files

- Strategy: `user_data/strategies/LeahAI.py`
- Config: `user_data/configs/config_lea.json`
- DB: `user_data/tradesv3_lea_v6.sqlite` (inside container)
- Snapshots: `/freqtrade/user_data/logs/trade_snapshots_v6.jsonl`
- Architecture: `docs/ARCHITECTURE_CONSOLIDATION.md`
