# Trading Bots Performance Analysis
**Date**: November 3, 2025
**Export Time**: 05:05 UTC
**Mode**: Dry-Run (Paper Trading)

---

## Bot Configuration

### Bot 1: LeaFreqAI Strategy
- **API Port**: 8080
- **Strategy**: LeaFreqAIStrategy
- **Model**: PyTorchMLPRegressor
- **Pairs**: UNI/BTC, LTC/BTC, ADA/BTC, BTC/USDT
- **Timeframe**: 5m
- **Max Open Trades**: 3
- **Stake Amount**: 0.30 BTC
- **Database**: tradesv3.sqlite

### Bot 2: FinAgent Strategy
- **API Port**: 8081
- **Strategy**: LeaFinAgentStrategy
- **Model**: PyTorchMLPRegressor
- **Pairs**: UNI/BTC, LTC/BTC, ADA/BTC, BTC/USDT
- **Timeframe**: 5m
- **Max Open Trades**: 3
- **Stake Amount**: 0.30 BTC
- **Database**: tradesv3_finagent.sqlite

---

## Bot 1: LeaFreqAI Strategy Performance

### Current Status
- **Running Since**: October 26, 2025
- **Runtime**: 7 days
- **Current Open Trades**: 2

### Open Positions
| Pair | Entry Date | Entry Price | Current Price | P&L % | P&L (BTC) | P&L (USD) |
|------|-----------|-------------|---------------|-------|-----------|-----------|
| UNI/BTC | Nov 1, 10:40 | 0.0000533 | 0.0000521 | -2.45% | -0.00772 | -$841.86 |
| LTC/BTC | Nov 1, 12:05 | 0.000896 | 0.000889 | -0.98% | -0.00317 | -$346.29 |

### Overall Metrics
- **Total Trades**: 22
- **Closed Trades**: 20
- **Open Trades**: 2
- **Win Rate**: 80.0% (16 wins / 4 losses)

### Profitability
- **Total P&L**: -4.13% (-0.0409 BTC / -$4,457.57)
- **Closed P&L**: -2.93% (-0.0290 BTC / -$3,165.61)
- **Average P&L per Trade**: -0.58%
- **Profit Factor**: 0.55
- **Expectancy**: -0.00145 BTC per trade
- **Expectancy Ratio**: -0.089

### Risk Metrics
- **Max Drawdown**: 5.32% (0.0533 BTC)
- **Max Drawdown Period**: Oct 28, 06:45 - Oct 31, 11:23
- **Current Drawdown**: 4.03% (0.0403 BTC)
- **Current Drawdown Start**: Oct 28, 06:45

### Trade Statistics
- **Average Trade Duration**: 9h 47m
- **Best Performing Pair**: LTC/BTC (+0.24%)
- **Total Trading Volume**: 13.76 BTC
- **First Trade**: October 26, 2025
- **Latest Trade**: November 1, 2025

---

## Bot 2: FinAgent Strategy Performance

### Current Status
- **Running Since**: October 27, 2025
- **Runtime**: 6 days
- **Current Open Trades**: 0

### Overall Metrics
- **Total Trades**: 54
- **Closed Trades**: 54
- **Open Trades**: 0
- **Win Rate**: 29.6% (16 wins / 38 losses)

### Profitability
- **Total P&L**: -3.03% (-0.0300 BTC / -$3,274.20)
- **Closed P&L**: -3.03% (-0.0300 BTC / -$3,274.20)
- **Average P&L per Trade**: -0.39%
- **Profit Factor**: 0.34
- **Expectancy**: -0.00056 BTC per trade
- **Expectancy Ratio**: -0.462

### Risk Metrics
- **Max Drawdown**: 3.18% (0.0315 BTC)
- **Max Drawdown Period**: Oct 27, 18:35 - Nov 1, 05:40
- **Current Drawdown**: 3.03% (0.0300 BTC)
- **Current Drawdown Start**: Oct 27, 18:35

### Trade Statistics
- **Average Trade Duration**: 2h 24m
- **Best Performing Pair**: LTC/BTC (-0.31%)
- **Total Trading Volume**: 16.08 BTC
- **First Trade**: October 27, 2025
- **Latest Trade**: November 2, 2025 (3 hours ago)

---

## Comparative Analysis

| Metric | LeaFreqAI | FinAgent | Winner |
|--------|-----------|----------|---------|
| Total Trades | 22 | 54 | FinAgent (more active) |
| Win Rate | 80.0% | 29.6% | **LeaFreqAI** |
| Total P&L % | -4.13% | -3.03% | FinAgent (less loss) |
| Total P&L BTC | -0.0409 | -0.0300 | FinAgent (less loss) |
| Profit Factor | 0.55 | 0.34 | **LeaFreqAI** |
| Max Drawdown | 5.32% | 3.18% | FinAgent (lower risk) |
| Avg Duration | 9h 47m | 2h 24m | FinAgent (faster) |
| Expectancy Ratio | -0.089 | -0.462 | **LeaFreqAI** |

---

## Key Observations

### LeaFreqAI Strategy
**Strengths:**
- Excellent win rate (80%)
- Better profit factor despite losses
- Higher expectancy per trade

**Weaknesses:**
- Higher drawdown (5.32%)
- Longer average trade duration
- Lower trading frequency (22 trades in 7 days)
- Currently holding 2 losing positions

### FinAgent Strategy
**Strengths:**
- More active trading (54 trades in 6 days)
- Faster trade execution (2h 24m avg)
- Lower drawdown (3.18%)
- No open positions currently

**Weaknesses:**
- Very poor win rate (29.6%)
- Significantly worse profit factor (0.34)
- Negative expectancy ratio
- 38 out of 54 trades were losses

---

## Recommendations

1. **LeaFreqAI Strategy**
   - Consider tightening stop-loss to reduce max drawdown
   - Review entry conditions for UNI/BTC and LTC/BTC positions
   - Win rate is good but overall profitability needs improvement

2. **FinAgent Strategy**
   - **Critical**: Win rate of 29.6% indicates strategy may need significant revision
   - Consider reviewing entry/exit signals
   - May benefit from more conservative entry conditions
   - Risk/reward ratio needs improvement

3. **Both Bots**
   - Currently in dry-run mode - DO NOT activate live trading until profitability improves
   - Consider backtesting with different parameters
   - Review FreqAI model training and predictions
   - Monitor for another 7-14 days before making strategy changes

---

## Data Files

- `lea_freqai_trades.json` - All trades from LeaFreqAI bot
- `finagent_trades.json` - All trades from FinAgent bot
- `lea_freqai_profit.json` - Detailed profit statistics for LeaFreqAI
- `finagent_profit.json` - Detailed profit statistics for FinAgent

---

## Next Steps

1. Analyze trade patterns in detail using the exported JSON files
2. Review FreqAI model predictions vs actual outcomes
3. Adjust strategy parameters based on findings
4. Continue paper trading with modifications
5. Set profitability targets before considering live trading
