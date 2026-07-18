# Go-Live Readiness Assessment

**Date:** 2026-07-17 (updated from 2026-03-27)
**Current Status:** 🟡 NOT READY — L0 paper run in progress
**Target:** L3 paper trading (50 trades) before capital deployment review

---

## Status Summary

| Component | Status |
|---|---|
| v4.4 model | ✅ Deployed — sole decision authority |
| Container | ✅ Running (`freqtrade-lea-new`, up 16h) |
| Config | ✅ `dry_run=true`, `force_v44_model=true` |
| Snapshot logging | ✅ Fixed and re-enabled (2026-07-17) |
| Stake sizing | ✅ Fixed — now reads v4.4 probability |
| Paper trades | ⬜ 1/50 v4.4 trades (L1 not reached) |
| Distribution | ⬜ L2 monitoring in progress |

---

## Trust Ladder Progress

| Stage | Trades | Criteria | Current |
|-------|--------|----------|---------|
| L0 | 1 | v4.4 generating signals | ✅ Done (Trade #16) |
| L1 | 10 | Snapshot logging verified, no crashes | ⬜ 1/10 |
| L2 | 25 | Distribution within ±5pp of training band | ⬜ 1/25 |
| L3 | 50 | Breakeven or better | ⬜ 1/50 |

---

## What's Ready

- [x] v4.4 model deployed and authoritative
- [x] Container running with bug-fixed strategy
- [x] Snapshot logging operational
- [x] Distribution monitoring (probwatch_v6) running
- [x] Dry-run config confirmed

## What's NOT Ready

- [ ] 50 v4.4 paper trades completed
- [ ] L1 snapshot logging verified (need next entry to confirm)
- [ ] L2 distribution gate cleared
- [ ] L3 profitability gate cleared
- [ ] Real capital account configured
- [ ] Real exchange API keys configured

---

## Current Architecture

v4.4 is a **15-feature XGBClassifier** predicting volatility expansion (ATR[i+12] > ATR[i] × 1.05). It runs inside the `freqtrade-lea-new` Docker container and overwrites FreqAI's native output using `force_v44_model=true`.

**Decision chain:**
1. FreqAI runs (output overwritten)
2. `_apply_v44_prediction()` runs v4.4 classifier → overwrites `&-target`
3. `populate_entry_trend()` reads v4.4 probability
4. `confirm_trade_entry()` validates with g1–g8 gate
5. Snapshot written → trade executed

Full diagram: `docs/ARCHITECTURE_CONSOLIDATION.md`

---

## Deployment Shape

- **Container:** `freqtrade-lea-new` (shad/freqtrade-lea-v5:latest)
- **Strategy:** `LeahAI` (class LeahAIV5Strategy, version 6.1)
- **DB:** `tradesv3_lea_v6.sqlite`
- **Pairs:** BTC/USDT, ETH/USDT, SOL/USDT, LINK/USDT
- **Timeframe:** 5m

---

## Go-Live Requirements

Before capital deployment, ALL of the following must be met:

1. L1: 10 v4.4 trades with valid snapshots — no crashes, no model failures
2. L2: 25 v4.4 trades — all 4 pairs within ±5pp of training distribution band
3. L3: 50 v4.4 trades — net P&L at or above breakeven (after fees)
4. Real exchange API keys configured with read + trade permissions
5. Emergency stop procedures documented and tested
6. Max position size and daily loss limit defined

---

## Timeline

No fixed date. Proceeds by evidence — paper trades are the gate.

- **2026-07-17:** Container restarted with bug-fixed strategy. L0 confirmed.
- **Next:** Wait for L1 (10 trades) — estimated 3–7 days at current signal rate
- **After L1:** Begin L2 distribution monitoring
- **After L3:** Capital deployment review
