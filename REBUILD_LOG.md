# LEA FreqAI Feature Rebuild Log

**Date:** 2026-05-18
**Status:** Paused — pre-rebuild diagnostic complete

---

## Baseline: What We Know

| Metric | Value |
|--------|-------|
| Feature count | 386 |
| Shift-2 lagged features | 128 (33%) |
| Exit mechanics | ✅ Working (ROI + stoploss both fire correctly) |
| Model retrain behavior | ⚠️ Retrains on every restart (not frozen despite config) |
| Root cause | Late-entry bias from lagged momentum features |

### Trade Performance (Trades 75-108, Post-Fix)

| Period | Trades | WR | P&L | Cause |
|--------|--------|-----|-----|-------|
| May 8-9 (23 trades) | 23 | 100% | +$4.74 | Good model, good regime |
| May 10-18 (11 trades) | 8 | 36% | -$4.20 | Model retrained on worsening data |
| **Total** | **34** | **85%** | **+$0.54** | Asymmetric win/loss |

### The Asymmetry Problem

| Metric | Winners (27) | Losers (4) |
|--------|-------------|------------|
| Avg P&L | +$0.18 | -$1.58 |
| Exit reason | 100% roi | 100% stoploss |
| Hold time | 3-17h | 31-37h |

**Winner/Loser asymmetry:** Small winners, catastrophic losers. System cannot recover from consecutive stoploss hits because winners don't compensate.

---

## The Hypothesis

### Question 1: Smallest Feature Set That Could Work

**Current-state indicators only** (no lagged/shifted features):

| Indicator | Timeframes | Features |
|-----------|------------|----------|
| RSI | 14, 20 | 2 per pair |
| MACD (line + signal + hist) | default | 3 per pair |
| Bollinger Bands position | 20 | 1 per pair |
| ATR | 14, 20 | 2 per pair |
| Current candle return | 5m, 15m | 2 per pair |
| Volume (relative to MA) | 20 | 1 per pair |

**Total: ~11 features per pair × 3 pairs = ~33 features + BTC correlation = ~50-60 total**

No shifted candles. No rolling windows beyond indicator calibration. No cross-pair features except BTC/USDT as market sentiment proxy.

### Question 2: Why This Will Work Better

**Lagged features cause momentum-chasing.** When a model learns that "positive returns in the last N candles predict continued upward movement," it fires entries AFTER the move has already started. By the time the model enters, momentum is already reversing.

Current-bar features (RSI, MACD) measure **current state**, not historical drift. RSI at 70 means overbought NOW — the model can act on that immediately. A shift-2 return feature at +2% means "returns were positive 2 candles ago" — by the time that signal fires, the move may already be over.

**The fix:** Replace momentum-drift features with mean-reversion indicators (RSI, Bollinger position) that fire on current extremes rather than historical patterns.

### Question 3: Kill Criteria

**Hard gates at 50 dry-run trades:**

| Metric | Pass | Fail |
|--------|------|------|
| Win Rate | ≥70% | <70% |
| Avg P&L | ≥$0.15/trade | <$0.15 |
| Max consecutive losses | ≤3 | >3 |
| Total trades | 50 | <50 in 4 weeks |

**If fail at 50 trades:** Document findings, mothball project. Do not continue with incremental tweaks. The architecture is wrong — start over or abandon.

**Hard abort during run:**
- 5 consecutive stoploss hits → pause immediately
- Cumulative DD >-$10 → pause immediately
- Any single day loss >-$3 → pause and reassess

---

## Execution Plan

### Saturday: Feature Engineering

- [ ] Audit current 386 features, classify by type
- [ ] Remove `include_shifted_candles` from config (set to 0)
- [ ] Reduce `indicator_periods_candles` to [14, 20] only
- [ ] Set `train_period_days: 60`
- [ ] Retrain model, verify feature count ~50-60
- [ ] Run backtest on historical period (Mar-Apr) to check generalization

### Sunday: Dry-Run Setup

- [ ] Switch to `dry_run: true`
- [ ] Start bot, monitor first 5 entries
- [ ] Verify prediction distribution (should span + and -, not clustered at 0)
- [ ] Run `monitor_rebuild.sh` daily

### Validation Timeline

| Phase | Trades | Duration | Goal |
|-------|--------|----------|------|
| Dry-run | 50 | 2-4 weeks | WR ≥70%, avg ≥$0.15 |
| If dry-run passes | 50 live | 2-4 weeks | Same metrics on real capital |
| **Total validation** | **100 trades** | **4-8 weeks** | Confirmed deployable system |

---

## What's Already Committed

- Config fix: `retrain: false`, `live_retrain_hours: 0` — working ✅
- Exit mechanics: ROI + stoploss both firing correctly ✅
- Diagnostic data: 34 trades fully documented ❌
- Feature reduction: **NOT YET STARTED** ← current task

---

## Current Branch

`main` — pre-rebuild snapshot
`feature-reduction-v1` — branch for rebuild (to be created)