# 🚀 LEA Bot - Quick Start Reference

> Historical note: this quickstart uses older paths and a previous single-bot deployment flow. Use `CURRENT_STATE.md` and `docs/systemd-services/README.md` for the current multi-bot service setup.

## ⚡ TL;DR - Start Your Bot

```bash
cd /home/pi/freqtrade
nano .env                    # Add your Binance API keys
./start_lea_bot.sh          # Start bot
tail -f freqtrade.log       # Watch logs
```

---

## 📝 Must Do FIRST

### 1. Edit .env File (2 minutes)
```bash
nano /home/pi/freqtrade/.env
```

**Change these lines:**
```bash
BINANCE_API_KEY=paste_your_real_key_here
BINANCE_API_SECRET=paste_your_real_secret_here
```

**Get keys from:** https://www.binance.com/en/my/settings/api-management

**Optional:** Add Telegram (or set `enabled: false` in config.json line 122)

---

## 🎯 Common Commands

### Start Bot
```bash
cd /home/pi/freqtrade
./start_lea_bot.sh              # Dry-run (safe)
./start_lea_bot.sh --background # Background mode
./start_lea_bot.sh --live       # REAL MONEY (careful!)
```

### Stop Bot
```bash
pkill -f "freqtrade trade"
```

### Check Status
```bash
source .venv/bin/activate
freqtrade status        # Current trades
freqtrade show_trades   # Trade history
freqtrade profit        # Performance summary
```

### View Logs
```bash
tail -f freqtrade.log                    # Live logs
tail -f user_data/logs/freqai.log       # AI training logs
grep ERROR freqtrade.log                # Just errors
```

### Access Web UI
Open: http://localhost:8080
- Username: `admin`
- Password: Check `.env` file for `API_PASSWORD`

---

## ✅ Verify Working

After starting, you should see:
- ✅ "Wallets synced"
- ✅ "Starting HTTP Server at 127.0.0.1:8080"
- ✅ "Application startup complete"
- ✅ No error messages

First run: Model training takes 5-15 minutes

---

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| Port 8080 in use | `pkill -f freqtrade` |
| Token rejected | Edit `.env` with real credentials |
| No trades | Wait for model training (check `user_data/logs/freqai.log`) |
| Bot won't start | Check logs: `tail -100 freqtrade.log` |

---

## 📊 Performance Monitoring

### Expected Performance (Based on Optimization Testing)

**In Bear Market (-23% decline):**
- Win Rate: ~83.5%
- Trades per Day: ~2.2
- Market Outperformance: +10-12%
- Max Drawdown: ~15%

**In Bull/Neutral Market:**
- Expected: Positive returns (10-20% estimated)
- Strategy optimized for risk management

### After 24 Hours:
```bash
source .venv/bin/activate
freqtrade show_trades
freqtrade profit
```

### After 1 Week:
```bash
source .venv/bin/activate
freqtrade backtesting --config config_lea_backtest.json \
  --strategy LeaFreqAIStrategy --timerange=20250901-
```

---

## 📱 Telegram Commands (if enabled)

In Telegram chat with your bot:
- `/status` - Current open trades
- `/profit` - Show profit summary
- `/balance` - Show wallet balance
- `/count` - Trade statistics
- `/help` - All commands

---

## 🚨 Important Safety Notes

1. **Always test in dry-run first** (default mode)
2. **Start with small capital** when going live
3. **Monitor first 24 hours closely**
4. **Set up stop-loss properly** (already configured at -15%)
5. **Never share .env file** (contains API keys)

---

## 📁 Key Files

- **Config:** `user_data/config.json`
- **Strategy:** `user_data/strategies/LeaFreqAIStrategy.py`
- **Model:** `user_data/freqaimodels/LeaTorchLSTM.py`
- **Logs:** `freqtrade.log`
- **Credentials:** `.env` (KEEP SECRET!)

---

## 🎓 Next Steps

1. **Day 1-3:** Monitor dry-run performance
2. **Day 4-7:** Analyze results, tweak if needed
3. **Week 2:** Consider live trading with small amount
4. **Week 3+:** Scale up based on performance

---

## 📚 Full Documentation

**Strategy & Performance:**
- **`LEA_STRATEGY_OPTIMIZATION.md`** - Complete optimization report & final configuration
- **`STOPLOSS_STRATEGY_TESTING.md`** - Detailed stoploss testing results
- **`LEA_PROGRESS.md`** - Full implementation progress & changelog

**Setup & Usage:**
- **`CURRENT_STATE.md`** - Current repo status and doc routing
- **`docs/systemd-services/README.md`** - Current service setup
- **`QUICK_START.md`** - This file (historical quick reference)
- **`docs/`** - Official FreqTrade documentation

---

**Status:** 🟢 Strategy optimized and production-ready!

**Performance:** 83.5% win rate, beating market by 12.44%

*For optimization details see `LEA_STRATEGY_OPTIMIZATION.md`*
