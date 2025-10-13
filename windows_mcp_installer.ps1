# FreqTrade MCP Installer for Claude Desktop
# Run this script on your Windows machine in PowerShell

Write-Host "╔════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   FreqTrade MCP Setup for Claude Desktop              ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "⚠️  Not running as Administrator (that's OK)" -ForegroundColor Yellow
}

# Step 1: Check Node.js
Write-Host "Step 1: Checking Node.js installation..." -ForegroundColor Green
try {
    $nodeVersion = node --version
    $npmVersion = npm --version
    Write-Host "✅ Node.js: $nodeVersion" -ForegroundColor Green
    Write-Host "✅ NPM: $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Node.js not found!" -ForegroundColor Red
    Write-Host "Please install from: https://nodejs.org" -ForegroundColor Yellow
    exit 1
}

# Step 2: Test FreqTrade API
Write-Host "`nStep 2: Testing FreqTrade API connection..." -ForegroundColor Green
$localUrl = "http://192.168.50.10:8080/api/v1/ping"
$vpnUrl = "http://10.240.89.1:8080/api/v1/ping"
$apiUrl = ""

try {
    $response = Invoke-RestMethod -Uri $localUrl -TimeoutSec 5
    if ($response.status -eq "pong") {
        Write-Host "✅ Local network connection successful!" -ForegroundColor Green
        $apiUrl = "http://192.168.50.10:8080"
    }
} catch {
    Write-Host "⚠️  Local network not accessible, trying VPN..." -ForegroundColor Yellow
    try {
        $response = Invoke-RestMethod -Uri $vpnUrl -TimeoutSec 5
        if ($response.status -eq "pong") {
            Write-Host "✅ VPN connection successful!" -ForegroundColor Green
            $apiUrl = "http://10.240.89.1:8080"
        }
    } catch {
        Write-Host "❌ Cannot reach FreqTrade API!" -ForegroundColor Red
        Write-Host "Please ensure:" -ForegroundColor Yellow
        Write-Host "  - FreqTrade is running on Raspberry Pi" -ForegroundColor Yellow
        Write-Host "  - You're on the same network OR connected to WireGuard VPN" -ForegroundColor Yellow
        $continue = Read-Host "Continue anyway? (y/n)"
        if ($continue -ne "y") {
            exit 1
        }
        $apiUrl = "http://192.168.50.10:8080"
    }
}

# Step 3: Create Claude config directory
Write-Host "`nStep 3: Creating Claude configuration directory..." -ForegroundColor Green
$claudeDir = "$env:APPDATA\Claude"
if (-not (Test-Path $claudeDir)) {
    New-Item -ItemType Directory -Force -Path $claudeDir | Out-Null
    Write-Host "✅ Created directory: $claudeDir" -ForegroundColor Green
} else {
    Write-Host "✅ Directory already exists: $claudeDir" -ForegroundColor Green
}

# Step 4: Create config file
Write-Host "`nStep 4: Creating MCP configuration..." -ForegroundColor Green
$configPath = "$claudeDir\claude_desktop_config.json"

# Check if config exists
$configExists = Test-Path $configPath
if ($configExists) {
    Write-Host "⚠️  Configuration file already exists!" -ForegroundColor Yellow
    $backup = "$claudeDir\claude_desktop_config.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
    Copy-Item $configPath $backup
    Write-Host "✅ Backup created: $backup" -ForegroundColor Green
}

# Configuration options
Write-Host "`nChoose configuration:" -ForegroundColor Cyan
Write-Host "1. Local network only (192.168.50.10)" -ForegroundColor White
Write-Host "2. VPN only (10.240.89.1)" -ForegroundColor White
Write-Host "3. Both (recommended - switch between them)" -ForegroundColor White
$choice = Read-Host "Enter choice (1-3)"

$config = @{}

switch ($choice) {
    "1" {
        $config = @{
            mcpServers = @{
                freqtrade = @{
                    command = "npx"
                    args = @("-y", "@modelcontextprotocol/create-server", "freqtrade-api")
                    env = @{
                        FREQTRADE_API_URL = "http://192.168.50.10:8080"
                        FREQTRADE_API_USERNAME = "admin"
                        FREQTRADE_API_PASSWORD = "f9l4fHChq8ky6HYY6ZKibw=="
                    }
                }
            }
        }
    }
    "2" {
        $config = @{
            mcpServers = @{
                freqtrade = @{
                    command = "npx"
                    args = @("-y", "@modelcontextprotocol/create-server", "freqtrade-api")
                    env = @{
                        FREQTRADE_API_URL = "http://10.240.89.1:8080"
                        FREQTRADE_API_USERNAME = "admin"
                        FREQTRADE_API_PASSWORD = "f9l4fHChq8ky6HYY6ZKibw=="
                    }
                }
            }
        }
    }
    "3" {
        $config = @{
            mcpServers = @{
                "freqtrade-local" = @{
                    command = "npx"
                    args = @("-y", "@modelcontextprotocol/create-server", "freqtrade-api")
                    env = @{
                        FREQTRADE_API_URL = "http://192.168.50.10:8080"
                        FREQTRADE_API_USERNAME = "admin"
                        FREQTRADE_API_PASSWORD = "f9l4fHChq8ky6HYY6ZKibw=="
                    }
                }
                "freqtrade-vpn" = @{
                    command = "npx"
                    args = @("-y", "@modelcontextprotocol/create-server", "freqtrade-api")
                    env = @{
                        FREQTRADE_API_URL = "http://10.240.89.1:8080"
                        FREQTRADE_API_USERNAME = "admin"
                        FREQTRADE_API_PASSWORD = "f9l4fHChq8ky6HYY6ZKibw=="
                    }
                }
            }
        }
    }
    default {
        Write-Host "❌ Invalid choice" -ForegroundColor Red
        exit 1
    }
}

# Save configuration
$config | ConvertTo-Json -Depth 10 | Set-Content -Path $configPath
Write-Host "✅ Configuration saved to: $configPath" -ForegroundColor Green

# Step 5: Verify configuration
Write-Host "`nStep 5: Verifying configuration..." -ForegroundColor Green
if (Test-Path $configPath) {
    Write-Host "✅ Configuration file created successfully" -ForegroundColor Green
    Write-Host "`nConfiguration content:" -ForegroundColor Cyan
    Get-Content $configPath | Write-Host -ForegroundColor White
} else {
    Write-Host "❌ Failed to create configuration file" -ForegroundColor Red
    exit 1
}

# Step 6: Instructions
Write-Host "`n╔════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                  Setup Complete!                       ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Close Claude Desktop completely (check system tray)" -ForegroundColor White
Write-Host "2. Restart Claude Desktop" -ForegroundColor White
Write-Host "3. Open a new conversation" -ForegroundColor White
Write-Host "4. Try: 'Check FreqTrade bot status'" -ForegroundColor White
Write-Host ""
Write-Host "Configuration location:" -ForegroundColor Cyan
Write-Host "  $configPath" -ForegroundColor White
Write-Host ""
Write-Host "API Details:" -ForegroundColor Cyan
Write-Host "  URL: $apiUrl" -ForegroundColor White
Write-Host "  Username: admin" -ForegroundColor White
Write-Host "  Password: f9l4fHChq8ky6HYY6ZKibw==" -ForegroundColor White
Write-Host ""

# Offer to open config directory
$openDir = Read-Host "Open configuration directory? (y/n)"
if ($openDir -eq "y") {
    explorer $claudeDir
}

Write-Host "`n✨ Setup complete! Restart Claude Desktop to activate MCP." -ForegroundColor Green
