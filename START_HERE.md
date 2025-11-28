# 🚀 START HERE - Dry Run Setup Guide

## You Have 3 Simple Steps to Start Trading Bot

### Step 1: Setup Telegram Alerts (5 min)
```bash
# TLDR Setup:
1. Open Telegram → Search "@BotFather"
2. Send: /newbot
3. Name: "FinAgent Trading Bot"
4. Username: "finagent_bot_YOURNAME" (must be unique)
5. Copy the TOKEN you receive
6. Open: https://api.telegram.org/bot[YOUR_TOKEN]/getUpdates
7. Send ANY message to your bot in Telegram
8. Find "id": XXXXX in the browser (your chat_id)
9. nano /home/bederf/freqtrade/config.json
10. Update telegram section:
    "telegram": {
        "enabled": true,
        "token": "YOUR_TOKEN",
        "chat_id": "YOUR_CHAT_ID"
    }
11. Save: Ctrl+O, Enter, Ctrl+X
```

### Step 2: Install Service (1 min)
```bash
sudo cp /tmp/freqtrade.service /etc/systemd/system/freqtrade.service && \
sudo systemctl daemon-reload && \
sudo systemctl enable freqtrade
```

### Step 3: Start Bot (1 min)
```bash
sudo systemctl start freqtrade
```

## Monitor Performance

Watch logs in real-time:
```bash
journalctl -u freqtrade -f
```

Check dashboard:
```
http://localhost:8080/ui/
```

Query trades:
```bash
sqlite3 user_data/trades.sqlite "SELECT * FROM trades ORDER BY open_date DESC LIMIT 5;"
```

## Essential Commands

| Command | What it does |
|---------|------------|
| `sudo systemctl start freqtrade` | Start bot |
| `sudo systemctl stop freqtrade` | Stop bot |
| `sudo systemctl status freqtrade` | Check status |
| `journalctl -u freqtrade -f` | Watch logs |
| `sudo systemctl restart freqtrade` | Restart bot |

## Success Metrics (After 7 Days)

✅ Win rate: 30-42% (backtest was 36.9%)
✅ Avg profit: -0.08% to -0.06% per trade
✅ Max drawdown: <1.5% (backtest was 0.38%)
✅ Total trades: ~45
✅ No critical errors

## Detailed Guides

- **DRY_RUN_GUIDE.md** - Complete dry run guide with troubleshooting
- **ALERTS_SETUP.md** - Alert options (Telegram, Discord, Email)
- **QUICK_START_DRY_RUN.md** - Quick reference

## Timeline

| Date | What's Happening |
|------|------------------|
| Dec 1 | Start dry run |
| Dec 1-7 | Monitor performance (7 days) |
| Dec 7 | Review metrics, make decision |
| Dec 8+ | Deploy to live trading (if metrics pass) |

## That's it!

Once you complete Step 1-3, the bot will trade automatically for 7 days.

**Questions?** Check the detailed guides or see documentation in the repo.

Good luck! 🎉
