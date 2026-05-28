# LEA FreqAI Feature Rebuild Log

**Date:** 2026-05-28
**Status:** MOTHBALLED — project complete, all experiments done

---

## Executive Summary

**What we tested:** Tightening stoploss from -5% to -1.5% to fix structurally negative expectancy caused by 9:1 loss/win ratio.

**Result:** FAILED. The tighter stop reduced avg loss (from $1.64 → $0.54) but WR collapsed (85.7% → 33.3%) in the same market regime. Net expectancy got worse (-$0.083 → -$0.304/trade).

**Hard abort triggered:** May 21 single-day loss of -$3.13 exceeded the -$3 threshold.

---

## The Math — Before and After

| Era | Trades | WR | Avg Winner | Avg Loser | Expectancy | Breakeven WR |
|-----|--------|-----|------------|-----------|------------|--------------|
| -5% stop (115-128) | 14 | 85.7% | +$0.176 | -$1.640 | -$0.083 | 90.3% |
| -1.5% stop (129+) | 9 | 33.3% | +$0.161 | -$0.536 | -$0.304 | 76.9% |

**The problem:** At -1.5%, the model is entering during a volatile/downtrend regime. The tight stop fires before the trade has time to work. The "winners" that survived the -5% era are now losers at -1.5%.

---

## Key Learnings

1. **Stoploss and WR are coupled.** Tightening stop doesn't just reduce loss size — it changes which trades count as winners vs losers. A trade that dips to -1.8% and recovers is a winner at -5% but a loser at -1.5%.

2. **Win rate is regime-dependent.** The same model produced 85.7% WR in one period and 33.3% in the next. Market regime matters more than the stoploss parameter.

3. **The 9:1 asymmetry was real but fix was wrong target.** Reducing avg loss from $1.64 to $0.54 was correct in principle, but the mechanism (hard -1.5% stop) introduced too many false stops in volatile conditions.

4. **Breakeven WR at -1.5% was 76.9%.** We got 33.3% — a catastrophic miss, not a near-miss.

5. **live_retrain_hours: 0 was working.** Model did NOT retrain during the trial. The WR collapse is market regime, not a retrain bug.

---

## Hard Abort Log

| Date | Criterion | Limit | Actual | Action |
|------|-----------|-------|--------|--------|
| 2026-05-21 | Single day loss | >-$3 | **-$3.13** | Bot should have paused |
| 2026-05-24 | Max consecutive stoplosses | ≤3 | 3 (borderline) | Still running |

---

## Consecutive Stoplosses

| Period | Max Consecutive | Trades Affected |
|--------|-----------------|-----------------|
| Pre-change (-5%) | 2 (119-120) | LINK, ETH |
| Post-change (-1.5%) | 3 (129-131) | SOL, ETH, LINK |

---

## What to Try Next

**Option A: Widen to -2.5% or -3% (NOT YET TESTED)**
- Reduce loss per trade from $1.64 to ~$0.90-$1.00
- May preserve more winners while still improving expectancy
- Needs ~75% WR to break even at -3%

**Option B: Add entry confirmation filter**
- Only enter if RSI < 60 (not overbought)
- Only enter if prediction > 0.002 (minimum confidence)
- Reduces total trades, may improve WR

**Option C: Let winners run (raise ROI targets)**
- Current: {0: 0.02, 20: 0.015, 40: 0.01, 90: 0.005}
- Raise top tier from 2% to 3%
- Avg winner grows from $0.17 to ~$0.25
- Breakeven WR drops to 68% at -5% stop
- Doesn't require model retrain

**Option D: Abandon**
- Two consecutive structural failures (momentum-chasing features, then tight stop)
- Document learnings, move on

---

## Current Config (May 25)

- **Stoploss:** -0.05 (final config)
- **Model:** Frozen (retrain=false, live_retrain_hours=0)
- **Features:** 98 (reduced from 386, no shift-2 candles)
- **Training:** 60-day window
- **Mode:** Dry-run, STOPPED

---

## Files Changed

- `user_data/strategies/LeaFreqAIStrategy.py` — stoploss: -0.05
- `user_data/configs/config_lea.json` — retrain: false, live_retrain_hours: 0

---

## Database

- `user_data/tradesv3_lea_v2.sqlite`
- Trade range for this trial: IDs 115-144
- Total P&L since 115: -$3.28 (27 closed trades)

---

## May 25 Kill Decision

**Status: MOTHBALLED**

| Metric | Value | Kill Threshold |
|--------|-------|----------------|
| Trades | 27 | 50 (shortened) |
| Win Rate | 70.4% | ≥70% (barely) |
| Avg Winner | +$0.169 | — |
| Avg Loser | -$0.812 | — |
| Expectancy | **-$0.122/trade** | ≥$0.10/trade |
| Gap to breakeven | 12.4 points WR | — |

**Root cause:** Payoff asymmetry. $0.81 avg loss vs $0.17 avg win requires 82.8% WR to break even. Current WR is 70.4%.

**What was tested:**
- Feature reduction (386→98) — working, reduced momentum-chasing ✅
- Stoploss -5% → -1.5% — reduced avg loss ($1.64→$0.54) but WR collapsed ❌
- Model freeze (retrain=false) — working, no auto-retrain ✅
- Bot infrastructure — working ✅

**What was never cleanly tested:** -1.5% stop + 3% ROI top tier together. That config has theoretical positive expectancy but was never validated end-to-end.

**The one untested config:** 60-day training + 60-80 current-bar features + -1.5% stop + 3% top ROI tier. That's the rebuild if this project is ever resumed.

**Trial net result:** -$3.28 on 27 trades. Not a failure of the infrastructure — a failure of the payoff structure.