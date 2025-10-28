# Trading Bot Performance Analysis

This directory contains detailed analysis reports of bot performance, issues, and recommendations.

## Latest Analysis: 2025-10-28

### Reports

1. **[Trade Analysis](TRADE_ANALYSIS_2025-10-28.md)** - Detailed analysis of why current trades are losing
2. **[Complete Summary](COMPLETE_SUMMARY_2025-10-28.md)** - Comprehensive overview of all findings and recommendations

## Key Findings

### Open Trade Issues

**UNI/BTC (-4.07%)**
- Entered at 24h high (0.00005930 BTC)
- Market reversed immediately after entry
- Only 0.9% from stop-loss trigger ⚠️

**LTC/BTC (-1.10%)**
- Entered near resistance
- Weak follow-through after entry
- Safe distance from stop-loss

### Strategy Issues Identified

1. **Entry threshold too low (0.2%)** → Generates too many signals
2. **No RSI overbought filter** → Can enter at market tops
3. **ML model too optimistic** → 71.9% bullish predictions
4. **ROI targets aggressive** → 2% immediate target hard to hit

### Performance Metrics

**Closed Trades:**
- Win Rate: 100% (4/4)
- Total Profit: +2.58% (+0.009 BTC / $1,029)
- Average Duration: 7h 50m

**All Trades (Including Open):**
- Total: 6 trades
- Overall P&L: -2.98%
- Unrealized Loss: -0.019 BTC (-$2,173)

### Recommendations

#### Immediate
1. Monitor UNI/BTC closely (near stop-loss)
2. Let LTC/BTC run (market bullish)
3. Observe Bot 2 training

#### Short-term
1. Increase entry threshold from 0.2% to 0.5%
2. Re-enable RSI < 70 filter
3. Implement trailing stop-loss

#### Long-term
1. Retrain model with 60+ days of data
2. Backtest new parameters
3. Compare Bot 1 vs Bot 2 performance

## Bot Configuration

### Bot 1: LEA-LSTM Strategy
- Port: 8080
- Status: Running with auto-start
- Open Trades: 2 (both losing)

### Bot 2: FinAgent Strategy
- Port: 8081
- Status: Running with auto-start
- Open Trades: 0 (just started)

## Files

- Strategy code: `user_data/strategies/`
- Configuration: `user_data/config*.json`
- Logs: `freqtrade*.log`
- Databases: `user_data/tradesv3*.sqlite`

