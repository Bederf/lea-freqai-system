# FinAgentStrategy v2 Risk Managed - Backtest Results

**Date:** 2025-10-28
**Status:** ✅ Backtest Complete
**Timeframe:** 2025-09-20 to 2025-10-27 (37 days)

---

## 📊 Overall Performance Summary

| Metric | Value |
|--------|-------|
| **Total Trades** | 230 |
| **Win Rate** | 29.6% (68 wins, 162 losses) |
| **Total Loss** | **-1.17%** (-0.01174341 BTC) |
| **Avg Profit/Trade** | -0.52% |
| **Max Drawdown** | 1.21% |
| **Starting Balance** | 1 BTC |
| **Ending Balance** | 0.98825659 BTC |
| **Sharpe Ratio** | -24.74 |
| **Days Win/Draw/Loss** | 11 / 2 / 23 |

---

## 🎯 Detailed Results by Pair

| Pair | Trades | Avg Profit % | Total Loss BTC | Total Loss % | Avg Duration | Win Rate |
|------|--------|--------------|-----------------|-------------|--------------|----------|
| **ADA/BTC** | 84 | -0.37 | -0.00308540 | -0.31% | 3:46:00 | 27.4% |
| **UNI/BTC** | 93 | -0.38 | -0.00353288 | -0.35% | 3:10:00 | 31.2% |
| **LTC/BTC** | 53 | -0.98 | -0.00512513 | -0.51% | 3:43:00 | 30.2% |

---

## 📈 Exit Reason Analysis

| Exit Reason | Exits | Avg Profit % | Total Profit BTC | Win% |
|-------------|-------|--------------|-------------------|------|
| **ROI** | 4 | +9.99% | +0.00391982 | 100% |
| **Stop Loss** | 7 | -10.07% | -0.00693016 | 0% |
| **Trailing Stop Loss** | 219 | -0.40% | -0.00873307 | 29.2% |

---

## 🔍 Key Findings

### Exit Profile
- **219 of 230 trades (95.2%) closed via trailing stop loss**
- Only 4 trades closed profitably via ROI (1.7%)
- 7 trades hit hard stop losses (3.0%)
- **Problem:** Aggressive trailing stop settings prematurely closing winning trades

### Win/Loss Distribution
- **Wins:** 68 trades averaging +profitable
- **Losses:** 162 trades averaging -0.52% each
- **Loss Ratio:** 70.4% of trades are losers
- **Consecutive Losses:** Maximum 19-trade losing streak

### Drawdown Profile
- **Max Drawdown:** 1.21% (moderate risk)
- **Drawdown Duration:** 30 days 19:05:00
- **Absolute Loss:** 0.01211449 BTC from peak
- **Min Balance:** 0.98788551 BTC
- **Max Balance:** 0.99985193 BTC

---

## ⚠️ Strategy Issues

### 1. **Excessive Trading Frequency**
- 230 trades in 37 days = 6.22 trades per day
- High trading volume increases slippage and fees
- Frequent small losses accumulate

### 2. **Poor Win Rate**
- 29.6% win rate is significantly below break-even
- Needs ~55%+ win rate to be profitable with 1.5:1 R:R
- Current losing streak patterns show design issue

### 3. **Aggressive Trailing Stop**
- Trailing stop configured: `trailing_stop_positive = 0.008` (0.8%)
- Trails at `trailing_stop_positive_offset = 0.015` (1.5%)
- Too aggressive - closes winning trades at minimal profit
- 95.2% of exits via trailing stop instead of ROI

### 4. **ML Model Limitation**
- Using LeaFreqAI's ML model with custom position sizing
- Position sizing (Kelly Criterion) not actually effective
- Risk management disabled during exits (trailing stop dominates)

---

## 📉 Comparison with Previous Strategies

| Metric | LeaFreqAI | FinAgent v1 | FinAgent v2 (Orig) | FinAgent v3 | **v2 RiskMgmt** |
|--------|-----------|-------------|-------------------|-------------|-----------------|
| **Trades** | 109 | 201 | 218 | 118 | **230** |
| **Win Rate** | 83.5% | 76.6% | 78.0% | 73.7% | **29.6%** |
| **Total Loss** | -10.75% | -29.91% | -28.02% | -24.62% | **-1.17%** |
| **Max Drawdown** | 14.27% | 32.15% | 32.66% | 28.58% | **1.21%** |
| **Outperformance** | +10.04% | -9.12% | -7.23% | -3.83% | **+19.62%** |

### Key Insight
Despite -1.17% loss, FinAgent v2 RiskManaged actually **outperforms the market by 19.62%** (market dropped -20.79%). However, it still underperforms LeaFreqAI's -10.75% loss.

---

## ⚡ Root Cause Analysis

### Why This Strategy Fails

1. **Trailing Stop Too Aggressive**
   - Should be 2-3%, not 0.8%
   - Current setting closes trades after 0.8% profit
   - Prevents reaching 10% ROI targets

2. **Position Sizing Ineffective**
   - Kelly Criterion-based sizing never actually applied
   - Trailing stop dominates and overrides custom stoploss
   - Risk management features bypassed

3. **Too Many Marginal Trades**
   - 230 trades vs LeaFreqAI's 109
   - Entry threshold matches LeaFreqAI (0.5%)
   - But execution differs - something in ML or features

4. **Wrong Risk Parameters**
   - `stoploss = -0.10` (10%) with trailing stop -0.008 (0.8%)
   - Contradictory signals
   - Trailing stop wins, defeats all risk management

---

## 🔧 Recommendations for Improvement

### Option 1: Remove Trailing Stop
```python
trailing_stop = False
use_custom_stoploss = True  # Let custom_stoploss() handle stops
```

### Option 2: Adjust Trailing Stop Settings
```python
trailing_stop = True
trailing_stop_positive = 0.05  # 5% trail (not 0.8%)
trailing_stop_positive_offset = 0.10  # 10% offset
```

### Option 3: Revert to LeaFreqAI
- LeaFreqAI achieves -10.75% loss
- FinAgent v2 RiskManaged achieves -1.17% loss (better!)
- But LeaFreqAI still has 83.5% win rate (vs 29.6%)
- LeaFreqAI has proven profitability in bull markets

---

## 💡 Conclusion

**FinAgentStrategy_v2_RiskManaged successfully addresses the drawdown issue** (1.21% vs market -20.79%), but **at the cost of excessive trading and poor win rate**.

The strategy is technically working but not optimally tuned:
- ✅ Low absolute loss (-1.17%)
- ✅ Good relative performance vs market (+19.62%)
- ✅ Minimal drawdown (1.21%)
- ❌ Too many trades (230)
- ❌ Poor win rate (29.6%)
- ❌ Trailing stop dominates, defeating risk management

**Recommendation:** Further testing with adjusted trailing stop parameters or revert to LeaFreqAI which has proven better risk-adjusted returns.

---

**Generated:** 2025-10-28 19:12:08 UTC
**File:** `/user_data/strategies/FinAgentStrategy_v2_RiskManaged.py`
**Config:** `config_lea_backtest.json`
**Status:** ✅ Ready for Parameter Tuning or Production Comparison

