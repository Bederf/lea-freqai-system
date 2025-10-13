# MCP Setup Verification Guide

## ✅ What You Just Did (Windows Side)

1. ✅ Ran `windows_mcp_installer.ps1`
2. ✅ Node.js detected (v22.14.0)
3. ✅ Selected Option 3 (Both local + VPN configs)
4. ✅ Configuration file created at `%APPDATA%\Claude\claude_desktop_config.json`

---

## 🔄 Next Steps (Complete the Setup)

### Step 1: Restart Claude Desktop

1. **Close Claude Desktop completely**
   - Click X on window
   - Check system tray (bottom right) - right-click Claude icon → Exit
   - Ensure it's fully closed

2. **Restart Claude Desktop**
   - Open from Start menu or desktop shortcut
   - Wait for it to fully load

### Step 2: Verify MCP Server Loaded

In Claude Desktop, look for:
- MCP indicator in the interface (usually bottom left or settings)
- Or check logs at: `%APPDATA%\Claude\logs\mcp.log`

---

## 🧪 Testing the Connection

### When Connected to Local Network (At Home)

In Claude Desktop, start a new conversation and try:

```
Check FreqTrade bot status
```

**Expected Response:**
- Bot status: RUNNING
- Current pairs being traded
- Model training status
- Dry-run mode confirmation

### When Connected via WireGuard VPN (Away from Home)

1. **First, connect to WireGuard:**
   - Open WireGuard app
   - Activate your tunnel
   - Verify connection (ping test below)

2. **Test VPN connectivity** (PowerShell):
   ```powershell
   Test-Connection -ComputerName 10.240.89.1 -Count 2
   ```

3. **In Claude Desktop, try:**
   ```
   Check FreqTrade bot status
   ```

---

## 🔍 Troubleshooting

### Issue 1: "MCP server not found" or "No MCP servers available"

**Check config file exists:**
```powershell
Test-Path "$env:APPDATA\Claude\claude_desktop_config.json"
Get-Content "$env:APPDATA\Claude\claude_desktop_config.json"
```

**Solution:**
- Ensure file exists and contains the JSON configuration
- Restart Claude Desktop again
- Check Claude Desktop logs

### Issue 2: "Cannot connect to FreqTrade API"

**Test API manually** (PowerShell):

**Local network:**
```powershell
Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/ping"
```

**VPN:**
```powershell
# First ensure WireGuard connected
Get-Service -Name "WireGuardTunnel*"

# Then test API
Invoke-RestMethod -Uri "http://10.240.89.1:8080/api/v1/ping"
```

**Expected:** `{"status":"pong"}`

**If fails:**
- Check you're on same network as Pi OR VPN connected
- Verify FreqTrade bot is running on Pi: `ps aux | grep freqtrade`
- Check firewall settings

### Issue 3: "Authentication failed"

**Verify credentials in config match:**
- Username: `admin`
- Password: `f9l4fHChq8ky6HYY6ZKibw==`

### Issue 4: MCP server starts but returns errors

**Check Claude Desktop MCP logs:**
```powershell
Get-Content "$env:APPDATA\Claude\logs\mcp.log" -Tail 50
```

---

## 📱 Quick Reference Commands

### Test Commands in Claude Desktop (After Setup)

Try these once MCP is working:

**Status & Info:**
- "Check FreqTrade status"
- "Show my FreqTrade bot configuration"
- "What version of FreqTrade is running?"
- "Show current pair whitelist"

**Trading Info:**
- "Show my current trades"
- "What's my FreqTrade profit?"
- "Show wallet balance"
- "Display daily performance"

**Model Status:**
- "Are FreqAI models trained?"
- "Show model training status"
- "When was the last model update?"

---

## 🌐 Network Connection Summary

| Scenario | Network | URL | MCP Server |
|----------|---------|-----|------------|
| **At Home** | Same WiFi | `http://192.168.50.10:8080` | `freqtrade-local` |
| **Away** | WireGuard VPN | `http://10.240.89.1:8080` | `freqtrade-vpn` |

Claude will automatically use the appropriate server based on which one can connect.

---

## ✅ Verification Checklist

**On Windows (PowerShell):**
- [ ] Node.js installed: `node --version`
- [ ] Config file exists: `Test-Path "$env:APPDATA\Claude\claude_desktop_config.json"`
- [ ] API reachable: `Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/ping"`

**On Raspberry Pi (SSH):**
- [ ] Bot running: `ps aux | grep "freqtrade trade"`
- [ ] API listening: `sudo ss -tlnp | grep 8080`
- [ ] Models training: `tail -f freqtrade.log | grep "Starting training"`

**In Claude Desktop:**
- [ ] Claude Desktop restarted
- [ ] MCP servers loaded
- [ ] Can query FreqTrade status
- [ ] Returns real bot data

---

## 🎯 Success Indicators

You'll know everything is working when:

1. ✅ Claude Desktop starts without MCP errors
2. ✅ You ask "Check FreqTrade status" and get real data
3. ✅ You can see:
   - Bot state (RUNNING)
   - Current pairs
   - Model status
   - Open trades (if any)
   - Profit/loss data

---

## 📊 Current Bot Status (as of setup)

**Raspberry Pi Status:**
- ✅ Bot running (PID 2710)
- ✅ API accessible on port 8080
- ✅ Network mode: 0.0.0.0 (all interfaces)
- 🔄 Models training (BTC/USDT in progress)
- ⏳ Trading will begin once models complete (~15-20 min)

**Network Access:**
- ✅ Local IP: 192.168.50.10:8080
- ✅ VPN IP: 10.240.89.1:8080
- ✅ WireGuard active (peer connected)

---

## 🔒 Security Reminders

- ✅ API requires authentication (username/password)
- ✅ Not exposed to internet
- ✅ Only accessible via local network or VPN
- ✅ Dry-run mode active (no real money)
- ⚠️ Never share `claude_desktop_config.json` file

---

## 📞 If You Need Help

1. **Check Claude Desktop logs:**
   ```powershell
   explorer "$env:APPDATA\Claude\logs"
   ```

2. **Check bot logs on Pi:**
   ```bash
   tail -50 /home/pi/lea-freqai-system/freqtrade.log
   ```

3. **Test API connectivity:**
   ```powershell
   Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/ping"
   ```

4. **Verify WireGuard (if using VPN):**
   ```powershell
   Get-Service -Name "WireGuardTunnel*"
   Test-Connection -ComputerName 10.240.89.1
   ```

---

## 🎉 You're Almost Done!

**Current Step:** Close and restart Claude Desktop

**After Restart:** Try asking Claude:
```
Check FreqTrade bot status
```

If you see real data about your bot, you're all set! 🚀

---

**Setup Date:** 2025-10-12
**Bot Status:** Operational, models training
**Next Milestone:** First trades in ~20-30 minutes
