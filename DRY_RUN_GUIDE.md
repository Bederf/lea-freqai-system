# Dry Run Trading Guide
**Purpose**: Validate bot performance in real market conditions without risking real capital
**Status**: Ready to use - config already supports dry run mode

---

## What is Dry Run?

Dry run mode means:
✅ **Real market data** - Uses actual market prices
✅ **Real signals** - Bot generates real trading signals
✅ **Simulated trades** - Orders don't execute on exchange
✅ **Virtual portfolio** - Trades recorded in local database
✅ **No capital risk** - 100% safe, no real money involved

---

## Current Configuration

Your `config.json` is already configured for dry run:

```json
{
    "dry_run": true,
    "stake_currency": "BTC",
    "stake_amount": "unlimited",
    "initial_state": "running",
    "strategy": "FinAgentStrategy_v2_RiskManaged",
    "api_server": {
        "enabled": true,
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8080
    }
}
```

### Key Settings Explained

| Setting | Value | Meaning |
|---------|-------|---------|
| `dry_run` | `true` | ✅ Simulated trading mode |
| `stake_amount` | "unlimited" | Use % of portfolio for each trade |
| `initial_state` | "running" | Bot starts automatically |
| `api_server` | enabled | Access dashboard & data |
| `strategy` | FinAgentStrategy_v2_RiskManaged | Deploy main optimized bot |

---

## How to Run Dry Run

### Option 1: Direct Command (Recommended)
```bash
# Start the bot with dry run
source .venv/bin/activate
freqtrade trade --strategy FinAgentStrategy_v2_RiskManaged --dry-run

# Bot will:
# ✅ Connect to Binance API (real prices)
# ✅ Load strategy and indicators
# ✅ Monitor 1h candles
# ✅ Generate trading signals
# ✅ Execute simulated trades
# ✅ Log to: logs/freqtrade.log
```

### Option 2: Docker (if you use Docker)
```bash
docker-compose up -d
# Runs with config.json settings (already set to dry_run: true)
```

### Option 3: Systemd Service (for running 24/7)
```bash
# If you have a systemd service configured
systemctl start freqtrade
systemctl status freqtrade
journalctl -u freqtrade -f
```

---

## What Happens During Dry Run

### 1. Startup (First 30 seconds)
```
✅ Loading configuration
✅ Validating strategy
✅ Connecting to Binance API
✅ Loading market data
✅ Calculating indicators
✅ Ready for trading
```

### 2. Continuous Trading Loop
```
Every 1 hour:
├─ Download 1h candle data
├─ Calculate indicators
├─ Generate entry/exit signals
├─ Execute simulated trades
└─ Log to database & files
```

### 3. Trade Lifecycle

**ENTRY (Buy)**:
```
[2025-12-01 10:00] Entry signal detected!
  • Pair: UNI/BTC
  • Price: 0.00215 BTC
  • Position: 10 BTC value
  • Stop Loss: 0.00200 BTC (-7%)
  • Take Profit: 0.00245 BTC (+14%)
  • Status: SIMULATED (not real)
```

**HOLDING**:
```
[2025-12-01 11:00] Position open
  • Entry: 0.00215 BTC
  • Current: 0.00222 BTC
  • Unrealized P&L: +3.2%
  • Time held: 1 hour
```

**EXIT (Sell)**:
```
[2025-12-01 14:00] Exit signal triggered!
  • Exit price: 0.00245 BTC
  • Profit: +14% (+0.003 BTC)
  • Hold time: 4 hours
  • Status: CLOSED
```

---

## Monitoring Dry Run

### 1. Real-time Dashboard
```bash
# Access dashboard at:
http://localhost:8080/ui/

# Features:
✅ Live trades in real-time
✅ Performance metrics
✅ Charts and graphs
✅ Signal generation log
```

### 2. Live Log Monitoring
```bash
# Watch logs in real-time
tail -f logs/freqtrade.log

# Key things to watch for:
✅ Entry signals: "[Strategy] Entry signal detected"
✅ Exits: "[Strategy] Exit signal triggered"
✅ Errors: "[ERROR]" or "[CRITICAL]"
✅ Performance: "[freqtrade] Profit from last 24h"
```

### 3. Database Queries
```bash
# Check trades in database
sqlite3 user_data/trades.sqlite

# View last 10 trades
SELECT * FROM trades ORDER BY open_date DESC LIMIT 10;

# Count total trades
SELECT COUNT(*) FROM trades;

# Calculate win rate
SELECT
  COUNT(*) as total,
  SUM(CASE WHEN profit_abs > 0 THEN 1 ELSE 0 END) as wins
FROM trades;
```

### 4. Performance Summary
```bash
# Get weekly performance
freqtrade show-config | grep -A 5 roi

# Check last backtest
cat user_data/backtest_results/.last_result.json | jq
```

---

## Success Metrics for Dry Run

Track these metrics during your dry run validation:

### Daily Checklist
```
Day 1 (Dec 1):
☐ Bot starts without errors
☐ Market data loads correctly
☐ At least 1 trade executed
☐ Win rate reasonable (not 0% or 100%)
☐ Logs are readable and informative

Day 2-3 (Dec 2-3):
☐ ~10 total trades executed
☐ Win rate 20-50% (target: ~37%)
☐ Avg loss per trade <0.2%
☐ Drawdown <1%
☐ No hanging or timeout errors

Day 4-7 (Dec 4-7):
☐ ~40-50 total trades (proportional)
☐ Win rate 30-42% (backtest was 36.9%)
☐ Avg profit -0.08% to -0.06% per trade
☐ Max drawdown <1.5%
☐ Consistent trade execution
```

### Success Criteria

✅ **Win Rate**: 30-42% (backtest benchmark: 36.9%)
```
Calculation: (winning trades / total trades) * 100
Target: ±5% of backtest performance
```

✅ **Average Profit**: -0.08% to -0.06% per trade
```
Calculation: sum(all trade profits) / count(trades)
Should match backtest baseline (-0.08%)
```

✅ **Max Drawdown**: <1.5% (backtest: 0.38%)
```
Peak balance drop during the period
Slightly higher than backtest is normal (real friction)
```

✅ **Consistency**: Trades every 1-2 days
```
Means: Entry signals are being generated
Abnormal: 0 trades for 3+ days suggests signal issue
```

---

## Expected vs Actual Performance

### Backtest Baseline (Oct 1 - Nov 5, 2025)
- Total trades: 198
- Win rate: 36.9%
- Avg profit: -0.08%
- Total profit: -0.17%
- Max drawdown: 0.38%

### Dry Run Targets (Dec 1-7, 2025)
- Expected trades: ~45 (proportional to 8-day period)
- Expected win rate: 35-38% (±1% acceptable)
- Expected avg profit: -0.10% to -0.06% per trade
- Expected max drawdown: 0.5-1.0%

### Why Numbers Might Differ

✅ **Acceptable Differences**:
- Win rate ±2-3% (market conditions vary)
- Drawdown slightly higher (slippage, spread)
- Trade frequency ±20% (market volatility)

❌ **Red Flags**:
- Win rate <25% or >50% (hypothesis broken)
- Max drawdown >2% (risk control issue)
- 0 trades for 3+ days (signal generation broken)
- Consistent losses >0.2% per trade (parameter mismatch)

---

## Troubleshooting Dry Run

### Problem: Bot Won't Start

**Check 1: Python Version**
```bash
python --version
# Should be: Python 3.11 or higher
```

**Check 2: Dependencies**
```bash
pip list | grep freqtrade
# Should show freqtrade version
```

**Check 3: Config Syntax**
```bash
freqtrade show-config | head -20
# Should show config without errors
```

**Check 4: API Connection**
```bash
# If it hangs here, Binance API is slow
freqtrade list-pairs --exchange binance
```

### Problem: No Trades Executing

**Check 1: Signal Generation**
```bash
grep "Entry signal\|Exit signal" logs/freqtrade.log | tail -20
# Should show signals being generated
```

**Check 2: Risk Manager**
```bash
grep "Risk manager\|portfolio heat" logs/freqtrade.log | tail -20
# May show trades rejected by risk limits
```

**Check 3: Pair Data**
```bash
# Check if OHLCV data is available
ls -lah user_data/data/binance/1h/
# Should show .csv files for UNI, ADA, LTC, etc
```

**Solution**:
```bash
# Download missing data
freqtrade download-data --exchange binance --pairs UNI/BTC ETH/BTC ADA/BTC
```

### Problem: High Losses (>0.2% per trade)

**Possible Causes**:
1. Market regime changed (bearish → bullish)
2. Parameters drifted from backtest
3. Liquidity issues (wide spreads)

**Solutions**:
1. Wait a few more days to collect more data
2. Re-run hyperopt on current market data
3. Check if backtest had sufficient data

---

## Running Multiple Strategies

Want to compare FinAgent vs LeaFreqAI?

### Sequential Testing
```bash
# Test FinAgent for 3 days
freqtrade trade --strategy FinAgentStrategy_v2_RiskManaged --dry-run
# Log results

# Stop and switch
# Test LeaFreqAI for 3 days
freqtrade trade --strategy LeaFreqAIStrategy --dry-run
# Log results

# Compare performance
```

### Parallel Testing (Advanced)
```bash
# Run two instances on different ports
# Terminal 1:
freqtrade trade --strategy FinAgentStrategy_v2_RiskManaged --db-url sqlite:///trades_finagent.sqlite

# Terminal 2:
freqtrade trade --strategy LeaFreqAIStrategy --db-url sqlite:///trades_leafreqai.sqlite

# Compare databases
```

---

## Switching from Dry Run to Live Trading

When dry run performance is good:

### Step 1: Reduce Capital Risk (Still Dry)
```json
{
    "dry_run": true,  // Keep true for now
    "stake_amount": 0.001,  // Change from "unlimited" to specific amount
    "max_stake": 0.001
}
```

### Step 2: Final Verification (Dry Run, 24 hours)
```bash
# Run 1 more day with specific stake amount
freqtrade trade --strategy FinAgentStrategy_v2_RiskManaged --dry-run
# Verify performance is still good
```

### Step 3: Enable Live Trading (REAL CAPITAL)
```json
{
    "dry_run": false,  // ⚠️ NOW TRADING REAL MONEY
    "stake_amount": 0.001,  // Small capital
    "max_stake": 0.001,
    "exchange": {
        "name": "binance",
        "key": "${BINANCE_API_KEY}",  // MUST be valid live key
        "secret": "${BINANCE_API_SECRET}"  // MUST be live secret
    }
}
```

### Step 4: Start Small, Monitor Hard
```bash
# Start with 0.001 BTC (~$30 at current prices)
freqtrade trade --strategy FinAgentStrategy_v2_RiskManaged

# Monitor CONSTANTLY
tail -f logs/freqtrade.log
# Watch dashboard: http://localhost:8080/ui/

# First red flag → STOP IMMEDIATELY
pkill -f freqtrade
```

---

## Dry Run Schedule Recommendation

**Week 1: Initial Dry Run (Dec 1-5)**
```
Dec 1:  Start dry run, monitor first 24 hours
Dec 2:  Review metrics, check for issues
Dec 3:  Accumulate more data (3 days)
Dec 4:  Stress test with rate changes
Dec 5:  Final analysis, decision point
```

**Decision at Dec 5**:
- ✅ **GO**: Metrics match backtest → Move to live with capital limits
- ⏸️ **NO-GO**: Issues found → Debug, retest, or revert

**Week 2: Live Trading with Limits (Dec 6-12)**
- Start with 0.001 BTC (small capital)
- Monitor 24/7
- If good after 3 days, increase to 0.002 BTC
- If issues, revert to dry run or pause

**Week 3+: Normal Operations (Dec 13+)**
- Scale capital based on performance
- Continue 24/7 monitoring
- Weekly performance reviews

---

## Monitoring Tools

### Essential Commands

```bash
# Watch logs in real-time
tail -f logs/freqtrade.log | grep -E "Entry\|Exit\|ERROR"

# Get performance stats
freqtrade show-trades

# Check current status
freqtrade status

# Get database summary
sqlite3 user_data/trades.sqlite \
  "SELECT COUNT(*), SUM(profit_abs), AVG(profit_percent) FROM trades;"

# List open trades
sqlite3 user_data/trades.sqlite \
  "SELECT * FROM trades WHERE is_open=1;"
```

### Dashboard Access
```
URL: http://localhost:8080/ui/
Username: (from config.json api_server.username)
Password: (from config.json api_server.password)
```

---

## Summary

### ✅ Recommended Approach

1. **Start with Dry Run** (Dec 1-5)
   - No capital risk
   - Real market data & signals
   - Validate bot performance
   - Collect 7 days of trading data

2. **Validate Metrics**
   - Win rate: 30-42%
   - Avg profit: -0.15% to -0.01%
   - Drawdown: <1.5%
   - Consistency: Trades every 1-2 days

3. **Go/No-Go Decision** (Dec 5)
   - If metrics good → Move to live trading
   - If issues found → Debug and retest

4. **Live Trading** (Dec 6+)
   - Start with 0.001 BTC (small)
   - Monitor closely (24/7 alerts)
   - Scale capital slowly if good
   - Maintain weekly reviews

---

**Ready to start dry run? Run this command:**
```bash
source .venv/bin/activate && freqtrade trade --strategy FinAgentStrategy_v2_RiskManaged --dry-run
```

**Next step:** Monitor for 24 hours and report back! 📊
