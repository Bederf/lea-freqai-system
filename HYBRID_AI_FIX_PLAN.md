# HybridAIStrategy Fix & FinAgentStrategy Plan

**Date:** 2025-10-28
**Status:** Option B Complete, Option C Created, Awaiting Backtests

---

## 📋 Option B: HybridAIStrategy Fix (COMPLETED)

### Problem
Bot 2 (HybridAIStrategy) had 12.5% win rate (1 win, 7 losses) due to:
- **Exit signals too aggressive** - 70% of trades exited via signal, not ROI
- **ROI targets too ambitious** - 8% / 5% / 3% / 1% (rarely hit)
- **Stoploss too loose** - -10% vs proven -5%
- **Trailing stop complexity** - Added unnecessary exits
- **Bug in position sizing** - Used "&-prediction" instead of "&-target"

### Solution Applied
Four critical fixes to `/user_data/strategies/HybridAIStrategy.py`:

#### 1. Disabled Exit Signals (Line 51)
```python
# BEFORE: use_exit_signal = True
# AFTER: use_exit_signal = False
```
**Impact:** No more aggressive MACD/RSI exits killing profitable trades

#### 2. Revised ROI Targets (Lines 37-42)
```python
# BEFORE:
minimal_roi = {"0": 0.08, "20": 0.05, "40": 0.03, "60": 0.01}

# AFTER:
minimal_roi = {"0": 0.020, "20": 0.015, "40": 0.010, "90": 0.005}
```
**Impact:** More achievable targets, more ROI hits

#### 3. Tightened Stoploss (Line 45)
```python
# BEFORE: stoploss = -0.10
# AFTER: stoploss = -0.05
```
**Impact:** Better risk control, matches proven LeaFreqAI setting

#### 4. Disabled Trailing Stop (Line 48)
```python
# BEFORE: trailing_stop = True
# AFTER: trailing_stop = False
```
**Impact:** Simpler logic, no premature profit-taking

#### 5. Fixed Position Sizing Bug (Line 305)
```python
# BEFORE: if "&-prediction" not in dataframe.columns:
# AFTER: if "&-target" not in dataframe.columns:
```
**Impact:** Dynamic position sizing now actually works

### Expected Results
- **Win Rate:** 12.5% → ~40-50% (matching LeaFreqAI)
- **Exits:** 70% via signal → 0% via signal (ROI only)
- **Risk:** Better controlled with -5% stoploss
- **ROI Hits:** More frequent with achievable targets

### Status
✅ Code fixes applied
⏳ Backtest running (Sept 20 - Oct 28, 2025)
⏳ Live validation pending

---

## 🤖 Option C: FinAgentStrategy Created (COMPLETED)

### What We Built
Full FinAgent-inspired strategy with 6 advanced modules:

#### 1. Pattern Memory Module
- Tracks successful patterns over time
- Hashes patterns for identification
- Records outcomes and calculates confidence (0.5 to 1.5x)
- Prunes patterns older than 30 days

#### 2. Market Regime Detector
- Identifies: trending_up, trending_down, volatile, ranging, uncertain
- Uses: ADX (trend strength), ATR (volatility), EMA (direction)
- Provides regime-specific position multipliers

#### 3. Normalized Indicator Engine
- Converts traditional indicators to -1 to +1 scale
- RSI → -1 to +1
- MACD → z-score normalized
- Bollinger Bands → position within bands
- Volume → surge detection
- Trend → EMA-based momentum
- Aggregates signals with dynamic weights

#### 4. Performance Memory
- Tracks regime-specific performance
- Calculates win rate and profit factor by regime
- Informs strategy adjustments

#### 5. Dynamic Position Sizing
- Combines: pattern confidence × regime performance
- Result: 0.5x to 1.5x position scaling
- Adapts to current conditions

#### 6. Conservative Exit Logic
- ROI table only (no exit signals)
- Fixed -5% stoploss
- No trailing stop
- Lessons learned from HybridAI's aggressive exits

### File Created
`/user_data/strategies/FinAgentStrategy.py` (400+ lines)

### Key Features
- ✅ All FinAgent components implemented
- ✅ Pattern memory with hashing
- ✅ Regime detection with multipliers
- ✅ Normalized indicators (5 types)
- ✅ Dynamic position sizing
- ✅ Conservative, proven exit logic
- ✅ Full FreqAI integration

### Status
✅ Strategy fully implemented
⏳ Backtest pending (comparison vs LeaFreqAI baseline)
⏳ Deployment pending (will replace HybridAIStrategy)

---

## 🎯 Next Steps

### Immediate (Now)
1. ⏳ Wait for HybridAI backtest results
2. ⏳ Run FinAgentStrategy backtest
3. Compare both fixed strategies

### Short-term (Today)
1. Deploy fixed HybridAI to Pi for live testing
2. Backtest FinAgent on full dataset
3. Compare FinAgent vs LeaFreqAI vs Fixed HybridAI

### Medium-term (Option C - This Week)
1. If FinAgent shows promise → replace HybridAI with it
2. Run both FinAgent and LeaFreqAI side-by-side
3. A/B test: FinAgent vs LeaFreqAI for 5-10 days

### Long-term (Optimization Phase)
1. Fine-tune pattern memory thresholds
2. Optimize regime detection parameters
3. Adjust position sizing multipliers
4. Consider ensemble approach (LeaFreqAI + FinAgent combined)

---

## 📊 Strategy Comparison

| Component | LeaFreqAI | HybridAI Fixed | FinAgent |
|-----------|-----------|----------------|----------|
| **ML Predictions** | ✅ | ✅ | ✅ |
| **Technical Filters** | ✅ | ✅ | ✅ |
| **Pattern Memory** | ❌ | ❌ | ✅ |
| **Regime Detection** | ❌ | ❌ | ✅ |
| **Exit Signals** | ❌ | ❌ | ❌ |
| **Dynamic Sizing** | ❌ | ✅ (fixed) | ✅ |
| **Complexity** | Low | Medium | High |
| **Expected Win Rate** | ~50% | ~40-50% | ~48-55% |

---

## 🧪 Testing Strategy

### Phase 1: Validation (This Week)
1. HybridAI backtest: Confirm fix improves win rate
2. FinAgent backtest: Validate pattern memory helps
3. Live trading: Both run simultaneously

### Phase 2: Optimization (Next Week)
1. Identify which regime performs best
2. Tune pattern memory thresholds
3. Adjust entry/exit filters if needed

### Phase 3: Production (End of Week)
1. If FinAgent proves better → Option C (replace HybridAI)
2. Run final backtests over 6 months of data
3. Deploy to live trading

---

## 🔧 Technical Details

### HybridAI Fix - Files Changed
- `/user_data/strategies/HybridAIStrategy.py`
  - Lines 37-51: ROI, stoploss, trailing_stop, exit_signal
  - Lines 251-269: populate_exit_trend (no exit signals)
  - Lines 305-317: custom_stake_amount (&-target fix)

### FinAgent - New Files
- `/user_data/strategies/FinAgentStrategy.py` (NEW, 400+ lines)
  - PatternMemory class
  - MarketRegimeDetector class
  - PerformanceMemory class
  - NormalizedIndicatorEngine class
  - FinAgentStrategy main class

### Configuration
Both strategies use same config:
- `config_lea_backtest.json` (for backtesting)
- `config_lea_dryrun.json` (for live testing)

---

## ✅ Checklist

### Option B: HybridAI Fix
- [x] Identify root causes (aggressive exits)
- [x] Apply 5 critical fixes
- [x] Code review (no issues found)
- [ ] Backtest on 40 days data
- [ ] Validate win rate improves
- [ ] Deploy to live trading
- [ ] Monitor for 5-10 trades

### Option C: FinAgentStrategy
- [x] Design all 6 modules
- [x] Implement pattern memory
- [x] Implement regime detection
- [x] Implement indicator normalization
- [x] Implement performance memory
- [x] Implement position sizing
- [x] Integrate all modules
- [ ] Backtest vs baseline
- [ ] Validate improvements
- [ ] Deploy alongside LeaFreqAI
- [ ] A/B test for 5-10 days
- [ ] Replace HybridAI if superior

---

**Generated:** 2025-10-28 16:15 UTC
**Status:** Phase 1 Complete - Awaiting Backtests
**Next Update:** When backtests complete
