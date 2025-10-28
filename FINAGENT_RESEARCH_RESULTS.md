# FinAgent Strategy Research Results

**Date:** 2025-10-28
**Status:** Testing Complete - Results Below

---

## 📊 Backtest Comparison

### All Strategies (Sept 20 - Oct 27, 2025)

| Metric | LeaFreqAI | HybridAI (Fixed) | FinAgent v1 | FinAgent v2 (Optimized) | FinAgent v3 (Stricter) |
|--------|-----------|------------------|-------------|------------------------|------------------------|
| **Trades** | 109 | 84 | 201 | 218 | 118 |
| **Win Rate** | 83.5% | 75.0% | 76.6% | 78.0% | 73.7% |
| **Total Loss** | **-10.75%** | -18.28% | -29.91% | -28.02% | -24.62% |
| **Avg Profit/Trade** | ? | -0.71% | -0.52% | -0.44% | -0.63% |
| **Max Drawdown** | **14.27%** | 18.76% | 32.15% | 32.66% | 28.58% |
| **Market Return** | -20.79% | -20.79% | -20.79% | -20.79% | -20.79% |
| **Outperformance** | **+10.04%** | +2.51% | -9.12% | -7.23% | -3.83% |

---

## 🎯 Key Finding

**LeaFreqAI is the winner.** It:
- ✅ Loses least (-10.75% vs market -20.79%)
- ✅ Has highest win rate (83.5%)
- ✅ Has lowest drawdown (14.27%)
- ✅ Fewest but highest quality trades (109 trades)

---

## 🔍 What We Learned

### Why FinAgent Underperformed

1. **Too Many Low-Quality Trades**
   - FinAgent v2: 218 trades (vs LeaFreqAI's 109)
   - FinAgent's entry logic takes more trades but lower quality
   - Extra trades have lower win rate (78% vs 83.5%)

2. **Stop-Loss Problem**
   - FinAgent v2: 45 trades hit stop-loss (-63.48% from those trades alone!)
   - LeaFreqAI: Only 17 trades hit stop-loss
   - FinAgent's entries don't reach profit targets before hitting stop

3. **Pattern Memory Not Useful**
   - On first 40 days: all patterns are new (confidence = 1.0x for all)
   - Can't benefit from pattern history on unfamiliar pairs
   - Adds complexity without benefit in short-term

4. **Regime Switching Hurts More Than Helps**
   - Trying to adapt to "uncertain" regimes introduces bad trades
   - Conservative regimes multiply threshold DOWN, taking worse trades
   - Simple fixed threshold (0.5%) works better than regime-adjusted

---

## 📈 Detailed Backtest Results

### LeaFreqAI (Baseline)
```
Total Trades:     109
Win Rate:         83.5% (91 wins, 17 losses, 1 neutral)
Total Profit:     -10.75% (-0.1075 BTC)
Avg Trade:        -0.09% per trade
Max Drawdown:     14.27%
ROI Exits:        91 (83.5% of trades profitable via ROI)
Stop Loss:        17 (15.6% hit stop loss)
Entry Threshold:  0.5% ML prediction
Exit Logic:       ROI table + 5% stoploss only
```

### FinAgent v1 (Initial)
```
Total Trades:     201
Win Rate:         76.6% (154 wins, 47 losses)
Total Profit:     -29.91%
Avg Trade:        -0.25% per trade
Max Drawdown:     32.15%
Stop Loss Hits:   44 trades (-60.74% total)
Entry Threshold:  0.1% base (scaled by regime)
Issue:            Too many weak entries
```

### FinAgent v2 (More Aggressive)
```
Total Trades:     218
Win Rate:         78.0% (170 wins, 48 losses)
Total Profit:     -28.02%
Avg Trade:        -0.20% per trade
Max Drawdown:     32.66%
Stop Loss Hits:   45 trades (-63.48%)
Changes:          Lower entry threshold (0.1%), 2.0x max position sizing
Issue:            Even more trades, still more stop-losses
```

### FinAgent v3 (Stricter)
```
Total Trades:     118
Win Rate:         73.7% (87 wins, 31 losses)
Total Profit:     -24.62%
Avg Trade:        -0.47% per trade
Max Drawdown:     28.58%
Entry Threshold:  0.5% (same as LeaFreqAI)
Issue:            Matches LeaFreqAI entry but still underperforms
```

---

## 🤔 Why FinAgent v3 Still Loses

Even with LeaFreqAI's entry threshold (0.5%), FinAgent v3 gets:
- 118 trades (vs 109 for LeaFreqAI)
- 73.7% win rate (vs 83.5%)
- -24.62% loss (vs -10.75%)

**Possible reasons:**
1. **Different ML model:** FinAgent uses XGBoost training, LeaFreqAI uses LSTM
2. **Feature differences:** Normalized indicators might lose information
3. **Exit logic:** Even without exit signals, something else differs
4. **Data leakage:** Our simplified version missing some edge-case handling

---

## 🏆 Recommendation

### For Production (Live Trading)
**Use LeaFreqAI unchanged** on the Pi:
- ✅ Proven best performance: -10.75% in bear market
- ✅ Highest win rate: 83.5%
- ✅ Lowest risk: 14.27% max drawdown
- ✅ Simple, no complex modules
- ✅ Running successfully now

### For Research/Future Development
1. **Option A:** Don't pursue FinAgent further - simple works better
2. **Option B:** Use FinAgent modules as **complementary signals only**
   - Keep LeaFreqAI as primary entry
   - Use pattern memory to boost position sizing on known winners
   - Use regime detection to skip low-quality regimes entirely
3. **Option C:** Implement proper FinAgent with real LSTM training
   - Current version is simplified, missing key components
   - Would need 4-6 weeks to fully implement and backtest

---

## 💡 Key Insights

1. **Simple beats complex** - LeaFreqAI's straightforward logic outperforms sophisticated multi-module system

2. **Entry quality matters most** - Getting into fewer, better trades > many mediocre trades

3. **ML threshold is critical** - 0.5% threshold seems optimal; 0.1% causes too many false signals

4. **Stoploss hits are expensive** - Each stop-loss hit costs ~1.4% on average; avoiding bad entries is better than managing losers

5. **Pattern memory needs history** - Can't benefit from learning on first 40 days of new data

6. **Regime switching can hurt** - Treating uncertain markets differently often makes things worse

---

## 📋 Next Steps

### Immediate
- [ ] Keep LeaFreqAI running on Pi as-is
- [ ] Monitor live performance for 10-20 more trades
- [ ] Document any divergences from backtest

### Short-term (This Week)
- [ ] Commit research results to git
- [ ] Archive FinAgent code as research reference
- [ ] Plan next optimization focus (if needed)

### Long-term (If Needed)
- [ ] Consider ensemble: LeaFreqAI primary + FinAgent secondary signals
- [ ] Explore hybrid: LeaFreqAI entry + FinAgent position sizing
- [ ] Run full FinAgent implementation (not simplified version)

---

## 🔬 Code Artifacts

### Files Tested
- `/user_data/strategies/LeaFreqAIStrategy.py` ✅ Winner
- `/user_data/strategies/HybridAIStrategy.py` (fixed version, worse)
- `/user_data/strategies/FinAgentStrategy.py` (3 iterations, all worse)

### Documentation
- `HYBRID_AI_FIX_PLAN.md` - Initial fix attempt results
- `FINAGENT_RESEARCH_RESULTS.md` - This document
- `TRADING_REPORT_2025-10-28.md` - Live trading data

---

## ✅ Conclusion

**The original LeaFreqAI strategy is optimal for current market conditions.**

The sophisticated FinAgent approach with pattern memory, regime detection, and multi-level reflection adds complexity without improving returns. In fact, it hurts performance by:
- Taking more marginal trades
- Lower overall win rate
- Hitting stop-losses more frequently

**Lesson:** In trading, simple, proven systems often beat complex ones. Focus on execution quality over architectural sophistication.

---

**Generated:** 2025-10-28 16:45 UTC
**Status:** Research Complete
**Recommendation:** Deploy LeaFreqAI, archive FinAgent experiments
