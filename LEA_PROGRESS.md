# LEA Strategy Implementation Progress

**Date:** 2025-10-06
**Status:** ✅ Initial Implementation Complete - Ready for Testing

---

## What We Built Today

### 1. **LSTM Model** ✅
**File:** `/home/pi/freqtrade/user_data/freqaimodels/LeaTorchLSTM.py`

**Features:**
- 2-layer LSTM with attention mechanism
- 128 hidden units, 25% dropout
- Sequence length: 48 candles
- Predicts future price returns (12 candles ahead)

**Architecture:**
```
Input (48 timesteps × features)
  → LSTM Layer 1 (128 units)
  → LSTM Layer 2 (128 units)
  → Attention Mechanism
  → Dense Layer (64 units)
  → Output (1 value: predicted return)
```

**Configuration:**
```json
"model_training_parameters": {
  "model_contract": "LeaTorchLSTM",
  "sequence": 48,
  "hidden": 128,
  "layers": 2,
  "dropout": 0.25,
  "use_attention": true,
  "epochs": 15,
  "batch_size": 64,
  "lr": 0.001,
  "weight_decay": 0.0001
}
```

---

### 2. **Base LEA Strategy** ✅
**File:** `/home/pi/freqtrade/user_data/strategies/LeaFreqAIStrategy.py`

**Key Features:**

**A. Stationary Feature Engineering**
- `%ret_1`, `%ret_3`, `%ret_12` - Price returns (1, 3, 12 candles)
- `%atr14_rel` - Relative ATR (volatility)
- `%rng_24` - 24-candle range
- `%z_48` - Z-score for mean reversion
- `%vol_z_48` - Volume anomaly detection
- RSI, MACD, Bollinger Bands

**B. Market Regime Detection**
- BTC trend correlation
- Market volatility measurement
- BTC dominance proxy

**C. Entry Signal Logic**
```python
ENTER when:
  - LSTM prediction > 0.0 (positive return expected)
  - RSI < 75 (not overbought)
  - Volume > 0
  - BTC trend > -10% (market not crashing)
  - Price > EMA 200 (uptrend)
```

**D. Exit Signal Logic**
```python
EXIT when:
  - LSTM prediction < 0.0 (negative return expected)
  - OR RSI > 85 (extreme overbought)
```

**E. Position Sizing**
- Dynamic sizing based on prediction confidence
- Multiplier: 0.5x to 1.5x of base stake
- Higher confidence = larger position

**F. Risk Management**
- Hard stoploss: -15%
- Trailing stop: Activates at +1% profit, trails at +2%
- ROI targets: 10% → 5% → 2% → 1%

---

### 3. **Configuration** ✅
**File:** `/home/pi/freqtrade/user_data/config.json`

**Settings:**
- Strategy: `LeaFreqAIStrategy`
- Dry run: Enabled
- Wallet: 235 USDT
- Max open trades: 3
- Pairs: BTC/USDT, ETH/USDT, BNB/USDT
- Timeframe: 5m (with 1h informative)
- FreqAI: Enabled
- Telegram: Enabled
- API Server: Port 8080

---

### 4. **Market Data** ✅
**Downloaded:** 30 days of historical data

**Pairs:**
- BTC/USDT: 8,889 candles (5m), 740 candles (1h)
- ETH/USDT: 8,889 candles (5m), 740 candles (1h)
- BNB/USDT: 8,889 candles (5m), 740 candles (1h)

**Location:** `/home/pi/freqtrade/user_data/data/binance/`

---

## Testing Status

### Initial Test Results
- ✅ Strategy loads successfully
- ✅ FreqAI initializes
- ✅ LSTM model structure validated
- ⏳ Model training in progress (first run)

**Note:** First run takes 5-15 minutes to train LSTM on historical data.

---

## How to Resume Tomorrow

### 1. Check Bot Status
```bash
cd /home/pi/freqtrade
source .venv/bin/activate

# Check if bot is running
ps aux | grep freqtrade

# View live logs
tail -f freqtrade.log
```

### 2. View Performance
```bash
# Check trades
freqtrade show_trades

# Check current status
freqtrade status

# Or use Telegram bot
# Or open FreqUI: http://localhost:8080
```

### 3. Stop/Start Bot
```bash
# Stop
pkill -f "freqtrade trade"

# Start
nohup freqtrade trade --config user_data/config.json > freqtrade.log 2>&1 &
```

---

## Next Steps (Priority Order)

### Phase 1: Monitor & Validate (Days 1-3)
- [ ] Let bot run for 24-48 hours in dry run
- [ ] Monitor prediction quality
- [ ] Check trade frequency (expect 2-5 trades/day)
- [ ] Validate stoploss triggers correctly
- [ ] Review Telegram notifications

### Phase 2: Analysis (Days 3-7)
- [ ] Run backtesting on 30-day data
- [ ] Compare backtest vs dry run results
- [ ] Analyze win rate and profit factor
- [ ] Review max drawdown

### Phase 3: Risk-Aware Upgrade (Week 2)
- [ ] Implement VaR/CVaR position sizing
- [ ] Add LLM sentiment integration (optional)
- [ ] Add circuit breaker protection
- [ ] Test with Risk-Aware strategy

### Phase 4: Live Trading (Week 3+)
- [ ] Final validation in dry run
- [ ] Start with small capital (10-20% of R4,000)
- [ ] Gradual scale-up based on performance

---

## Important Files

### Strategy Files
```
/home/pi/freqtrade/user_data/strategies/
├── LeaFreqAIStrategy.py        # Main strategy (ACTIVE)
└── LeaRiskAwareStrategy.py     # Template for future upgrade
```

### Model Files
```
/home/pi/freqtrade/user_data/freqaimodels/
└── LeaTorchLSTM.py             # LSTM model implementation
```

### Data Files
```
/home/pi/freqtrade/user_data/data/binance/
├── BTC_USDT-5m.json
├── BTC_USDT-1h.json
├── ETH_USDT-5m.json
├── ETH_USDT-1h.json
├── BNB_USDT-5m.json
└── BNB_USDT-1h.json
```

### Config Files
```
/home/pi/freqtrade/user_data/
├── config.json                 # Main configuration
└── tradesv3.dryrun.sqlite     # Dry run database
```

### Logs
```
/home/pi/freqtrade/
├── freqtrade.log              # Main bot log
└── user_data/logs/            # FreqAI training logs
```

---

## Performance Expectations

### Base LEA Strategy (What We Built)
- **Win Rate:** 48-55%
- **Trades per Day:** 2-5
- **Sharpe Ratio Target:** 1.2-1.6
- **Max Drawdown:** 20-30%
- **Average Hold Time:** 4-8 hours

### Success Metrics to Track
1. **Prediction Accuracy:** LSTM forecast vs actual returns
2. **Risk-Adjusted Returns:** Sharpe ratio > 1.0
3. **Drawdown Control:** Max DD < 25%
4. **Trade Quality:** Profit factor > 1.4

---

## Troubleshooting

### Bot Won't Start
```bash
# Check logs
tail -100 freqtrade.log

# Common issues:
# - Missing API keys (should work in dry run)
# - FreqAI training timeout (normal on first run)
# - Port 8080 already in use
```

### No Trades Happening
```bash
# Check if model trained
ls -la user_data/models/

# Check predictions
freqtrade show_predictions

# Possible reasons:
# - Model still training (wait 5-15 min)
# - No entry signals (market conditions)
# - All slots full (max 3 trades)
```

### Model Training Errors
```bash
# Check FreqAI logs
tail -100 user_data/logs/freqai.log

# Common fixes:
# - Ensure PyTorch installed
# - Check GPU/CPU compatibility
# - Verify data downloaded correctly
```

---

## Resources

### Freqtrade Docs
- Strategy: `/home/pi/freqtrade/docs/strategy-customization.md`
- FreqAI: `/home/pi/freqtrade/docs/freqai.md`
- Configuration: `/home/pi/freqtrade/docs/configuration.md`

### Commands Reference
```bash
# Trade commands
freqtrade trade --config config.json
freqtrade backtesting --config config.json --strategy LeaFreqAIStrategy
freqtrade hyperopt --config config.json --hyperopt-loss SharpeHyperOptLoss

# Data commands
freqtrade download-data --pairs BTC/USDT ETH/USDT --days 30
freqtrade list-data

# Analysis commands
freqtrade show_trades
freqtrade plot-dataframe --pair BTC/USDT
freqtrade plot-profit
```

---

## GitHub Sync

### Files to Commit (Next Session)
- `user_data/freqaimodels/LeaTorchLSTM.py`
- `user_data/strategies/LeaFreqAIStrategy.py`
- `user_data/config.json`
- `LEA_PROGRESS.md` (this file)

### Git Commands
```bash
cd /home/pi/freqtrade
git add user_data/freqaimodels/LeaTorchLSTM.py
git add user_data/strategies/LeaFreqAIStrategy.py
git add user_data/config.json
git add LEA_PROGRESS.md

git commit -m "Implement LEA LSTM strategy with FreqAI

- Add LeaTorchLSTM model with attention mechanism
- Create LeaFreqAIStrategy with stationary features
- Configure FreqAI with 48-candle sequence
- Download 30 days market data for BTC/ETH/BNB
- Enable dry run testing with 235 USDT wallet

🤖 Generated with Claude Code"

git push origin main
```

---

## Questions to Answer Tomorrow

1. **Did the model train successfully?**
   - Check for model files in `user_data/models/`
   - Look for training completion in logs

2. **Are predictions being generated?**
   - Check `&-prediction` column in dataframe
   - Values should be between -0.1 and 0.1

3. **Is the bot making trades?**
   - Check `freqtrade show_trades`
   - Telegram notifications

4. **What's the prediction quality?**
   - Compare predictions to actual price movements
   - Calculate prediction accuracy

---

**Summary:** LEA base strategy is ready. Let it run overnight in dry run mode. Tomorrow we'll check performance and decide if we need the Risk-Aware upgrade.

**Status:** 🟢 All systems operational, model training in progress
