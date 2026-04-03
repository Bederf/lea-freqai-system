# Quick Start Guide - Freqtrade Dry Run

> Historical note: this file documents an older single-service dry-run flow. Current operations use per-bot `tradesv3_*.sqlite` databases and the service/scripts documented in `CURRENT_STATE.md`.

## ⚡ 3-Step Setup (5 minutes)

### Step 1: Install Systemctl Service
```bash
# Copy service file
sudo cp /tmp/freqtrade.service /etc/systemd/system/freqtrade.service

# Reload systemctl
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable freqtrade

# Verify installation
sudo systemctl status freqtrade
```

### Step 2: Configure Alerts (Choose ONE)

#### Option A: Telegram (EASIEST - 5 min)
```bash
# 1. Create bot with BotFather in Telegram
# 2. Get token & chat_id
# 3. Edit config
nano config.json

# 4. Find "telegram" section and update:
"telegram": {
    "enabled": true,
    "token": "YOUR_TOKEN_HERE",
    "chat_id": "YOUR_CHAT_ID_HERE"
}

# 5. Save (Ctrl+O, Enter, Ctrl+X)
```

#### Option B: Discord (10 min)
```bash
# 1. Create Discord server
# 2. Create webhook
# 3. Edit config:
nano config.json

# 4. Add webhook:
"webhook": {
    "enabled": true,
    "url": "YOUR_WEBHOOK_URL"
}

# 5. Save
```

### Step 3: Start the Bot
```bash
# Start bot (will run in background)
sudo systemctl start freqtrade

# Check status
sudo systemctl status freqtrade

# Watch logs (real-time)
journalctl -u freqtrade -f

# To stop:
sudo systemctl stop freqtrade
```

## 📊 Monitoring

### Dashboard
```
http://localhost:8080/ui/
```

### Live Logs
```bash
journalctl -u freqtrade -f
```

### Trades Database
```bash
sqlite3 user_data/trades.sqlite "SELECT * FROM trades ORDER BY open_date DESC LIMIT 5;"
```

## 📝 Commands

```bash
# Start
sudo systemctl start freqtrade

# Stop
sudo systemctl stop freqtrade

# Status
sudo systemctl status freqtrade

# Logs (real-time)
journalctl -u freqtrade -f

# Logs (errors only)
journalctl -u freqtrade -f | grep ERROR

# Restart
sudo systemctl restart freqtrade
```

## ✅ Success Checklist

- [ ] Service installed
- [ ] Alerts configured (telegram/discord)
- [ ] Bot started
- [ ] Received first alert
- [ ] Dashboard working
- [ ] First trade executed within 24 hours

## 🎉 You're Ready!

Run: `sudo systemctl start freqtrade` then monitor with `journalctl -u freqtrade -f`
