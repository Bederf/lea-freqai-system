# FreqTrade Remote Access Setup Guide

**Last Updated:** 2025-10-12
**Status:** ✅ Configured for Local Network + WireGuard Access

---

## 📡 Network Configuration

### **Raspberry Pi Network Info**
- **Local IP:** `192.168.50.10`
- **WireGuard VPN IP:** `10.240.89.1`
- **FreqTrade API Port:** `8080`
- **API Mode:** Network accessible (0.0.0.0)

### **Access URLs**

| Connection Type | URL | Use When |
|----------------|-----|----------|
| **Local Network** | `http://192.168.50.10:8080` | At home on same WiFi |
| **WireGuard VPN** | `http://10.240.89.1:8080` | Away from home via VPN |
| **Localhost** | `http://localhost:8080` | SSH'd into Pi |

---

## 🔐 API Credentials

```
Username: admin
Password: f9l4fHChq8ky6HYY6ZKibw==
JWT Secret: 84312ad80c27693794efc52c671240030ad6a3193cbdf23efb17f221d36d12bd
```

⚠️ **Keep these credentials secure! Never commit to git or share publicly.**

---

## 🧪 Testing API Connection

### **1. Test from Local Network (Windows PC)**

Open PowerShell and run:

```powershell
# Test basic connectivity
Test-NetConnection -ComputerName 192.168.50.10 -Port 8080

# Test API ping
Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/ping"
```

Expected response:
```json
{"status": "pong"}
```

### **2. Test from WireGuard VPN**

When connected to WireGuard:

```powershell
# Verify WireGuard connected
Get-Service -Name "WireGuardTunnel*"

# Test API ping
Invoke-RestMethod -Uri "http://10.240.89.1:8080/api/v1/ping"
```

### **3. Get JWT Token**

```powershell
$body = @{
    username = "admin"
    password = "f9l4fHChq8ky6HYY6ZKibw=="
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/token/login" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body

$token = $response.access_token
Write-Host "Token: $token"
```

### **4. Test Authenticated Endpoint**

```powershell
# Get bot status
$headers = @{
    "Authorization" = "Bearer $token"
}

Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/status" `
    -Headers $headers
```

---

## 🔌 MCP Server Configuration

### **For Claude Code / MCP Clients**

Add this to your MCP configuration file:

**Location:**
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Mac/Linux: `~/.config/claude-code/config.json`

**Configuration:**

```json
{
  "mcpServers": {
    "freqtrade-local": {
      "command": "npx",
      "args": ["@modelcontextprotocol/server-freqtrade"],
      "env": {
        "FREQTRADE_API_URL": "http://192.168.50.10:8080",
        "FREQTRADE_USERNAME": "admin",
        "FREQTRADE_PASSWORD": "f9l4fHChq8ky6HYY6ZKibw=="
      }
    },
    "freqtrade-vpn": {
      "command": "npx",
      "args": ["@modelcontextprotocol/server-freqtrade"],
      "env": {
        "FREQTRADE_API_URL": "http://10.240.89.1:8080",
        "FREQTRADE_USERNAME": "admin",
        "FREQTRADE_PASSWORD": "f9l4fHChq8ky6HYY6ZKibw=="
      }
    }
  }
}
```

**Note:** You can switch between `freqtrade-local` (home) and `freqtrade-vpn` (away) as needed.

---

## 📱 Available API Endpoints

### **Bot Status & Info**
- `GET /api/v1/ping` - Health check (no auth)
- `GET /api/v1/version` - Bot version
- `GET /api/v1/status` - Current trades
- `GET /api/v1/balance` - Wallet balance
- `GET /api/v1/profit` - Profit summary
- `GET /api/v1/performance` - Performance by pair
- `GET /api/v1/daily` - Daily stats

### **Trade Management**
- `GET /api/v1/trades` - All trades
- `POST /api/v1/forceexit` - Force exit trade
- `POST /api/v1/forceenter` - Force entry (if enabled)

### **Bot Control**
- `POST /api/v1/start` - Start trading
- `POST /api/v1/stop` - Stop trading
- `POST /api/v1/stopbuy` - Stop new entries
- `POST /api/v1/reload_config` - Reload config

### **Configuration**
- `GET /api/v1/show_config` - Show config
- `GET /api/v1/whitelist` - Current pairs
- `GET /api/v1/blacklist` - Blacklisted pairs

Full API documentation: https://www.freqtrade.io/en/stable/rest-api/

---

## 🛡️ Security Considerations

### ✅ **What's Protected**
- API requires authentication (username/password + JWT)
- WireGuard encrypts all VPN traffic
- Only accessible on local network or via VPN
- Not exposed to public internet

### ⚠️ **Security Best Practices**

1. **Firewall Rules** (Optional - More Security)
   ```bash
   # On Raspberry Pi, allow only local network + WireGuard
   sudo ufw allow from 192.168.50.0/24 to any port 8080
   sudo ufw allow from 10.240.89.0/24 to any port 8080
   sudo ufw enable
   ```

2. **Change Default Password** (Recommended)
   - Edit `/home/pi/lea-freqai-system/user_data/config.json`
   - Change `api_server.password` value
   - Restart FreqTrade

3. **Monitor Access Logs**
   ```bash
   grep "api_server" /home/pi/lea-freqai-system/freqtrade.log
   ```

4. **Rotate JWT Secret** (Periodically)
   - Generate new secret: `openssl rand -hex 32`
   - Update in config.json

---

## 🔄 Restarting After Config Changes

When you modify `config.json`, restart the bot:

```bash
# Stop bot
pkill -9 -f "freqtrade trade"

# Start bot with new config
cd /home/pi/lea-freqai-system
source .venv/bin/activate
nohup freqtrade trade \
    --config user_data/config.json \
    --strategy LeaFreqAIStrategy \
    --freqaimodel LeaTorchLSTM \
    --logfile freqtrade.log > /dev/null 2>&1 &

# Check it started
ps aux | grep "freqtrade trade" | grep -v grep
```

---

## 🌐 WireGuard Connection Guide

### **On Windows Client:**

1. **Install WireGuard**
   - Download: https://www.wireguard.com/install/
   - Install WireGuard for Windows

2. **Import Configuration**
   - Open WireGuard app
   - Click "Add Tunnel" → "Add empty tunnel" or import `.conf` file
   - Activate the tunnel

3. **Verify Connection**
   ```powershell
   # Check WireGuard service
   Get-Service -Name "WireGuardTunnel*"

   # Ping Raspberry Pi
   Test-Connection -ComputerName 10.240.89.1 -Count 4
   ```

4. **Test FreqTrade Access**
   ```powershell
   Invoke-RestMethod -Uri "http://10.240.89.1:8080/api/v1/ping"
   ```

### **On Raspberry Pi (Server):**

```bash
# Check WireGuard status
sudo wg show

# See connected peers
sudo wg show wg0

# Restart WireGuard
sudo systemctl restart wg-quick@wg0

# View logs
sudo journalctl -u wg-quick@wg0 -f
```

---

## 📊 Monitoring & Troubleshooting

### **Check if API is Accessible**

```bash
# From Raspberry Pi
curl http://localhost:8080/api/v1/ping

# Check what's listening on port 8080
sudo netstat -tlnp | grep 8080
# or
sudo ss -tlnp | grep 8080
```

### **Check FreqTrade Logs**

```bash
# API-related logs
tail -f /home/pi/lea-freqai-system/freqtrade.log | grep "api_server"

# All errors
grep ERROR /home/pi/lea-freqai-system/freqtrade.log | tail -20

# Recent activity
tail -50 /home/pi/lea-freqai-system/freqtrade.log
```

### **Common Issues**

| Problem | Solution |
|---------|----------|
| Connection refused | Check FreqTrade is running: `ps aux \| grep freqtrade` |
| Timeout | Check firewall: `sudo ufw status` |
| Authentication failed | Verify credentials match config.json |
| Can't reach via VPN | Check WireGuard connected: `sudo wg show` |
| Port 8080 in use | Kill old process: `pkill -9 -f freqtrade` |

---

## 🎯 Quick Reference

### **Access URLs**
```
Local:  http://192.168.50.10:8080
VPN:    http://10.240.89.1:8080
Web UI: Same URLs (use browser)
```

### **Credentials**
```
User: admin
Pass: f9l4fHChq8ky6HYY6ZKibw==
```

### **Test Command**
```powershell
# From Windows
Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/ping"
```

### **View Trades**
```powershell
# Get JWT token first, then:
$headers = @{"Authorization" = "Bearer $token"}
Invoke-RestMethod -Uri "http://192.168.50.10:8080/api/v1/status" -Headers $headers
```

---

## 📚 Additional Resources

- **FreqTrade REST API Docs:** https://www.freqtrade.io/en/stable/rest-api/
- **FreqTrade WebUI Docs:** https://www.freqtrade.io/en/stable/freq-ui/
- **WireGuard Docs:** https://www.wireguard.com/quickstart/
- **MCP Protocol:** https://modelcontextprotocol.io/

---

## 🚀 Next Steps

1. ✅ API configured to accept network connections
2. ⏳ Restart FreqTrade bot (required!)
3. ⏳ Test local network access from Windows
4. ⏳ Test WireGuard VPN access
5. ⏳ Configure MCP in Claude Code
6. ⏳ Test MCP commands

**Status:** Configuration complete, restart required for changes to take effect.

---

**Last Modified:** 2025-10-12
**Configuration File:** `/home/pi/lea-freqai-system/user_data/config.json`
**Log File:** `/home/pi/lea-freqai-system/freqtrade.log`
