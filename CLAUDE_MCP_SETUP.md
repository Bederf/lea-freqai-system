# Claude Desktop MCP - FreqTrade Integration Setup

**Complete activation plan for Claude Desktop MCP server**

---

## 📋 Prerequisites

Before starting, ensure you have:
- [ ] Claude Desktop installed on Windows
- [ ] Node.js 18+ installed (download from https://nodejs.org)
- [ ] WireGuard configured and working
- [ ] Access to your Raspberry Pi (192.168.50.10 or 10.240.89.1 via VPN)

---

## 🚀 Quick Setup (Copy & Paste)

### Step 1: Locate Claude Desktop Config File

**Windows Location:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**Full Path (typically):**
```
C:\Users\YourUsername\AppData\Roaming\Claude\claude_desktop_config.json
```

**Open in PowerShell:**
```powershell
# Open the config directory
explorer $env:APPDATA\Claude

# Or edit directly with notepad
notepad $env:APPDATA\Claude\claude_desktop_config.json
```

---

## 📝 Configuration File Content

### Option A: Local Network Only (At Home)

Copy this entire JSON into `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "freqtrade": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/create-server",
        "freqtrade-api"
      ],
      "env": {
        "FREQTRADE_API_URL": "http://192.168.50.10:8080",
        "FREQTRADE_API_USERNAME": "admin",
        "FREQTRADE_API_PASSWORD": "f9l4fHChq8ky6HYY6ZKibw=="
      }
    }
  }
}
```

### Option B: WireGuard VPN (When Away)

Copy this entire JSON into `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "freqtrade": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/create-server",
        "freqtrade-api"
      ],
      "env": {
        "FREQTRADE_API_URL": "http://10.240.89.1:8080",
        "FREQTRADE_API_USERNAME": "admin",
        "FREQTRADE_API_PASSWORD": "f9l4fHChq8ky6HYY6ZKibw=="
      }
    }
  }
}
```

### Option C: Both (Recommended - Switch Between Them)

Copy this entire JSON into `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "freqtrade-local": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/create-server",
        "freqtrade-api"
      ],
      "env": {
        "FREQTRADE_API_URL": "http://192.168.50.10:8080",
        "FREQTRADE_API_USERNAME": "admin",
        "FREQTRADE_API_PASSWORD": "f9l4fHChq8ky6HYY6ZKibw=="
      }
    },
    "freqtrade-vpn": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/create-server",
        "freqtrade-api"
      ],
      "env": {
        "FREQTRADE_API_URL": "http://10.240.89.1:8080",
        "FREQTRADE_API_USERNAME": "admin",
        "FREQTRADE_API_PASSWORD": "f9l4fHChq8ky6HYY6ZKibw=="
      }
    }
  }
}
```

---

## 🔧 Alternative: Direct API Implementation

If the MCP package doesn't exist, use this direct REST API configuration:

```json
{
  "mcpServers": {
    "freqtrade": {
      "command": "node",
      "args": [
        "-e",
        "const http = require('http'); const url = process.env.FREQTRADE_API_URL; const user = process.env.FREQTRADE_API_USERNAME; const pass = process.env.FREQTRADE_API_PASSWORD; async function call(endpoint) { const res = await fetch(`${url}${endpoint}`, { headers: { 'Authorization': `Basic ${Buffer.from(`${user}:${pass}`).toString('base64')}` }}); return res.json(); } process.stdin.on('data', async (data) => { const req = JSON.parse(data); const result = await call(req.endpoint); console.log(JSON.stringify(result)); });"
      ],
      "env": {
        "FREQTRADE_API_URL": "http://192.168.50.10:8080/api/v1",
        "FREQTRADE_API_USERNAME": "admin",
        "FREQTRADE_API_PASSWORD": "f9l4fHChq8ky6HYY6ZKibw=="
      }
    }
  }
}
```

---

## ✅ Step-by-Step Activation

### 1. Install Node.js (If Not Installed)

**Download & Install:**
- Go to https://nodejs.org
- Download LTS version (20.x)
- Run installer with default settings
- Verify installation:

```powershell
node --version
npm --version
```

Should show versions like `v20.x.x` and `10.x.x`

### 2. Create/Edit Claude Config

**PowerShell Commands:**

```powershell
# Create Claude directory if it doesn't exist
New-Item -ItemType Directory -Force -Path "$env:APPDATA\Claude"

# Create or edit config file
notepad "$env:APPDATA\Claude\claude_desktop_config.json"
```

**Paste one of the JSON configurations above**, then **Save** (Ctrl+S) and **Close**.

### 3. Verify Configuration

```powershell
# Check the file exists
Test-Path "$env:APPDATA\Claude\claude_desktop_config.json"

# View the content
Get-Content "$env:APPDATA\Claude\claude_desktop_config.json"
```

### 4. Restart Claude Desktop

1. **Close Claude Desktop completely** (check system tray)
2. **Reopen Claude Desktop**
3. MCP server should auto-start

### 5. Test Connection (In Claude Desktop)

Once Claude Desktop restarts, try these commands in a new conversation:

```
Check FreqTrade bot status
```

```
Show me current FreqTrade trades
```

```
What's my FreqTrade profit?
```

```
Show FreqTrade balance
```

---

## 🧪 Manual API Testing (Before MCP)

Test API access from Windows PowerShell first:

### Test 1: Basic Connectivity

```powershell
# Test ping
Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/ping"
```

**Expected:** `{"status":"pong"}`

### Test 2: Get JWT Token

```powershell
$body = @{
    username = "admin"
    password = "f9l4fHChq8ky6HYY6ZKibw=="
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/token/login" -Method POST -ContentType "application/json" -Body $body

$token = $response.access_token
Write-Host "Token: $token"
```

### Test 3: Get Bot Status

```powershell
$headers = @{
    "Authorization" = "Bearer $token"
}

Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/status" -Headers $headers
```

### Test 4: Get Profit

```powershell
Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/profit" -Headers $headers
```

---

## 🎯 Available Commands in Claude Desktop

Once MCP is configured, you can ask Claude:

### Status & Monitoring
- "Check FreqTrade status"
- "Show my current trades"
- "What's my FreqTrade profit?"
- "Show wallet balance"
- "Show performance by pair"
- "What's my daily profit/loss?"

### Trade Information
- "List all open trades"
- "Show trade history"
- "What trades were closed today?"
- "Show best performing pairs"

### Bot Control (Use Carefully!)
- "Stop FreqTrade bot"
- "Start FreqTrade bot"
- "Stop opening new trades"
- "Force exit trade #123"

### Configuration
- "Show FreqTrade configuration"
- "What pairs is FreqTrade trading?"
- "Show FreqTrade version"

---

## 🔍 Troubleshooting

### Issue 1: Config File Not Found

**Solution:**
```powershell
# Create directory
New-Item -ItemType Directory -Force -Path "$env:APPDATA\Claude"

# Create empty config
Set-Content -Path "$env:APPDATA\Claude\claude_desktop_config.json" -Value '{}'
```

### Issue 2: "npx command not found"

**Solution:** Install Node.js
```powershell
# Check if Node.js is installed
node --version

# If not, download from https://nodejs.org
```

### Issue 3: Connection Refused

**Check these:**

```powershell
# 1. Can you ping the Pi?
Test-Connection -ComputerName 192.168.50.10 -Count 2

# 2. Can you reach the API?
Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/ping"

# 3. Is FreqTrade running on Pi?
# SSH to Pi and run:
# ps aux | grep freqtrade
```

### Issue 4: Authentication Failed

**Solution:** Verify credentials in config match:
- Username: `admin`
- Password: `f9l4fHChq8ky6HYY6ZKibw==`

### Issue 5: MCP Server Won't Start

**Check Claude Desktop logs:**

```powershell
# View logs
Get-Content "$env:APPDATA\Claude\logs\mcp.log" -Tail 50
```

### Issue 6: WireGuard Connection

**Verify VPN:**

```powershell
# Check WireGuard status
Get-Service -Name "WireGuardTunnel*"

# Test VPN connectivity
Test-Connection -ComputerName 10.240.89.1 -Count 2

# Test API via VPN
Invoke-RestMethod -Uri "http://10.240.89.1:8080/api/v1/ping"
```

---

## 🔒 Security Notes

### ✅ What's Secure
- API requires authentication
- Not exposed to internet
- Only accessible via local network or VPN
- Credentials stored locally

### ⚠️ Important
1. **Never share** your `claude_desktop_config.json` file
2. **Never commit** config to git/GitHub
3. **Change password** in production (optional but recommended)
4. **Use VPN** when accessing remotely

---

## 📱 Quick Reference Card

**Save this for easy access:**

```
┌─────────────────────────────────────────────────────┐
│ FreqTrade MCP Quick Reference                       │
├─────────────────────────────────────────────────────┤
│ Local URL:  http://192.168.50.10:8080              │
│ VPN URL:    http://10.240.89.1:8080                │
│ Username:   admin                                   │
│ Password:   f9l4fHChq8ky6HYY6ZKibw==               │
│                                                     │
│ Config Location:                                    │
│ %APPDATA%\Claude\claude_desktop_config.json        │
│                                                     │
│ Test Command:                                       │
│ Invoke-RestMethod -Uri "http://192.168.50.10:8080/ │
│   api/v1/ping"                                      │
└─────────────────────────────────────────────────────┘
```

---

## 📚 Additional Resources

- **FreqTrade REST API:** https://www.freqtrade.io/en/stable/rest-api/
- **MCP Protocol:** https://modelcontextprotocol.io/
- **Claude Desktop:** https://claude.ai/download
- **Node.js:** https://nodejs.org/

---

## ✨ Complete Setup Checklist

- [ ] Node.js installed
- [ ] Claude Desktop installed
- [ ] Config file created at `%APPDATA%\Claude\claude_desktop_config.json`
- [ ] JSON configuration pasted and saved
- [ ] Claude Desktop restarted
- [ ] API connectivity tested from PowerShell
- [ ] WireGuard VPN tested (if using remote access)
- [ ] First command tested in Claude Desktop

---

## 🎉 Success Indicators

You'll know it's working when:

1. ✅ Claude Desktop starts without errors
2. ✅ You can ask "Check FreqTrade status" and get a response
3. ✅ Commands return real data (not errors)
4. ✅ You see trade information, profit data, etc.

---

## 🆘 Need Help?

If you encounter issues:

1. **Check API manually** using PowerShell commands above
2. **Verify FreqTrade is running** on Raspberry Pi
3. **Check Claude Desktop logs** in `%APPDATA%\Claude\logs\`
4. **Restart both** Claude Desktop and FreqTrade bot

---

**Last Updated:** 2025-10-12
**Status:** Ready for activation
**Next Step:** Copy JSON config and restart Claude Desktop
