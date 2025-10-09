# 🚀 LEA Bot - Quick Start Reference

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

### After 24 Hours:
```bash
freqtrade show_trades
freqtrade profit
```

### After 1 Week:
```bash
freqtrade backtesting --config user_data/config.json \
  --strategy LeaFreqAIStrategy --timerange=20241001-
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

- Setup fixes: `LEA_STARTUP_FIXED.md`
- Strategy details: `LEA_PROGRESS.md`
- FreqTrade docs: `docs/` directory

---

**Status:** 🟢 All startup issues fixed. Bot ready to run!

*Quick reference - For detailed info see LEA_STARTUP_FIXED.md*
