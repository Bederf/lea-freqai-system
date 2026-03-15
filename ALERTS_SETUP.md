# Alerts Configuration Guide
**Easiest to Hardest**: Telegram > Discord > Email

---

## 🔔 Option 1: Telegram (EASIEST - Recommended)

### Why Telegram?
✅ **Instant mobile notifications**
✅ **No server needed**
✅ **Free and simple**
✅ **Works from anywhere**
✅ **Native bot integration in Freqtrade**

### Setup (5 minutes)

**Step 1: Create Telegram Bot**
```
1. Open Telegram app
2. Search for "BotFather" (@BotFather)
3. Send: /start
4. Send: /newbot
5. BotFather asks: "Alright, a new bot. How are we going to call it?"
6. Type: "FinAgent Trading Bot" (or your name)
7. BotFather asks: "Good. Now choose a username for your bot."
8. Type: "finagent_trading_bot_YOURNAME" (must be unique)
9. BotFather returns:
   ✅ API Token: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
   ✅ Bot link: https://t.me/finagent_trading_bot_YOURNAME
10. Copy the API token (you'll need this)
```

**Step 2: Get Your Chat ID**
```
1. Search for your bot: @finagent_trading_bot_YOURNAME
2. Click Start
3. Send any message to the bot
4. Go to: https://api.telegram.org/bot123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11/getUpdates
   (Replace "123456:ABC-..." with YOUR token)
5. You'll see JSON with your chat ID (looks like: "id": 987654321)
6. Save your chat ID
```

**Step 3: Update config.json**
```json
{
    "telegram": {
        "enabled": true,
        "token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "chat_id": "987654321"
    }
}
```

**Step 4: Test**
```bash
# Restart the bot
sudo systemctl restart freqtrade

# Send test message
# You should receive a message in Telegram
```

### What You'll Receive
```
📊 [FinAgent] Entry Signal
Pair: UNI/BTC
Price: 0.00215 BTC
Stake: 0.0043 BTC
Profit Target: +14%

💰 [FinAgent] Trade Closed
Pair: UNI/BTC
Profit: +3.2% (+0.0001 BTC)
Duration: 4h 23m

⚠️ [FinAgent] Error
Bot stopped due to critical error
Check logs: tail -f logs/freqtrade.log
```

### Cost: FREE ✅

---

## 🎮 Option 2: Discord (MODERATE - Pretty UI)

### Why Discord?
✅ **Beautiful formatted messages**
✅ **Embed images and charts**
✅ **Multi-channel organization**
✅ **Server-based (more reliable)**
❌ Takes 10 minutes to set up

### Setup (10 minutes)

**Step 1: Create Discord Server**
```
1. Open Discord
2. Click "+" button to create server
3. Name: "Trading Bot"
4. Create
```

**Step 2: Create Webhook**
```
1. Right-click #general channel
2. Edit Channel → Integrations
3. Webhooks → New Webhook
4. Name: "FinAgent Bot"
5. Copy Webhook URL (looks like):
   https://discordapp.com/api/webhooks/123456789/ABCdef-ghi
```

**Step 3: Update config.json**
```json
{
    "webhook": {
        "enabled": true,
        "url": "https://discordapp.com/api/webhooks/123456789/ABCdef-ghi"
    }
}
```

**Step 4: Restart & Test**
```bash
sudo systemctl restart freqtrade
# Should receive messages in Discord
```

### Cost: FREE ✅

---

## 📧 Option 3: Email (HARDEST - Traditional)

### Why Email?
✅ **Traditional & reliable**
✅ **Works everywhere**
❌ Takes 15 minutes to set up
❌ Requires SMTP server
❌ Slower than chat apps

### Setup (15 minutes)

**Step 1: Get SMTP Credentials**

**Using Gmail:**
```
1. Go to myaccount.google.com
2. Security → App passwords
3. Select: Mail & Windows/Linux Device
4. Google generates app password (16 characters)
5. Save it
```

**Using Other Providers:**
- **Outlook**: Use your email & password
- **SendGrid**: Create free account, get API key
- **AWS SES**: Complex, not recommended

**Step 2: Update config.json**
```json
{
    "mail": {
        "enabled": true,
        "from_addr": "your-email@gmail.com",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "username": "your-email@gmail.com",
        "password": "your-16-char-app-password"
    }
}
```

**Step 3: Restart & Test**
```bash
sudo systemctl restart freqtrade
# Check your email inbox (may take 30 seconds)
```

### Cost: FREE (if using Gmail) ✅

---

## 🎯 My Recommendation

### For Dry Run Testing
**Use Telegram** (10 min setup, instant notifications)
- Get entry/exit alerts on your phone instantly
- Test for 7 days
- Verify bot is working as expected

### Command Summary
```bash
# 1. Create Telegram bot with BotFather (5 min)
# 2. Get your chat ID (2 min)
# 3. Update config.json (1 min):
nano /home/bederf/freqtrade/config.json

# 4. Paste this into telegram section:
{
    "telegram": {
        "enabled": true,
        "token": "YOUR_TOKEN_HERE",
        "chat_id": "YOUR_CHAT_ID_HERE"
    }
}

# 5. Save (Ctrl+O, Enter, Ctrl+X)
# 6. Restart bot:
sudo systemctl restart freqtrade
```

---

## Setup Comparison

| Feature | Telegram | Discord | Email |
|---------|----------|---------|-------|
| **Setup Time** | 5 min | 10 min | 15 min |
| **Mobile Push** | ✅ Yes | ✅ Yes | ⚠️ Slow |
| **Instant** | ✅ <1 sec | ✅ <1 sec | ❌ 30 sec |
| **Cost** | FREE | FREE | FREE |
| **Requires Server** | ❌ No | ✅ Yes | ✅ Yes |
| **Complexity** | Easy | Medium | Hard |
| **Reliability** | ✅ High | ✅ High | ⚠️ Medium |

**Winner**: 🏆 **Telegram** (easiest + fastest)

---

## Alert Types Available

### Entry Alerts
```
When: Bot detects buy signal
Contains:
- Pair name (UNI/BTC)
- Entry price
- Position size
- Stop loss level
- Take profit target
```

### Exit Alerts
```
When: Trade closes (profit or loss)
Contains:
- Pair name
- Exit price
- Profit/Loss %
- Trade duration
- Reason (target/stop loss/signal)
```

### Error Alerts
```
When: Bot encounters error
Contains:
- Error message
- Timestamp
- Recommended action
- Logs location
```

### Daily Summary (Optional)
```
Time: 00:00 UTC
Contains:
- Total trades (day)
- Win rate
- Total profit
- Max drawdown
- Current status
```

---

## Step-by-Step Telegram Setup

### TLDR Setup (Copy-Paste)
```
1. Open Telegram → Search "BotFather"
2. Send: /start
3. Send: /newbot
4. Name: FinAgent Trading Bot
5. Username: finagent_trading_bot_12345 (change 12345)
6. Copy token (you'll see it)
7. Open browser → https://api.telegram.org/bot[TOKEN]/getUpdates
   (Replace [TOKEN] with your token)
8. Send any message to your bot in Telegram
9. Refresh browser → find "id": XXXXXX (that's your chat_id)
10. Edit /home/bederf/freqtrade/config.json:
    ```json
    "telegram": {
        "enabled": true,
        "token": "[YOUR_TOKEN]",
        "chat_id": "[YOUR_CHAT_ID]"
    }
    ```
11. Save and restart:
    sudo systemctl restart freqtrade
12. Should receive "Bot started" message in Telegram ✅
```

---

## Verification

**After setup, you should receive:**

1. ✅ "Bot started" message when bot launches
2. ✅ Entry signals when trades open
3. ✅ Exit signals when trades close
4. ✅ Error alerts if anything goes wrong

**If you receive nothing:**
```bash
# Check if telegram is enabled in config
grep -A 3 '"telegram"' config.json

# Check bot logs
journalctl -u freqtrade -f | grep -i telegram

# Verify token format
# Token should be: 123456:ABC-DEFghijk...
```

---

## Quick Links

**Telegram BotFather**: https://t.me/BotFather
**Discord Webhooks Docs**: https://discord.com/developers/docs/resources/webhook
**Freqtrade Telegram Docs**: https://www.freqtrade.io/en/latest/telegram/

---

## Summary

✅ **Recommendation**: Use **Telegram** (easiest, fastest, free)
⏱️ **Setup Time**: 5-10 minutes
💰 **Cost**: Free
📱 **Push Notifications**: Yes (on your phone)
🔔 **Latency**: <1 second

**Next Step**: Pick one alert method and follow setup!
