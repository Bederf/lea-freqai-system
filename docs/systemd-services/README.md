# Systemd Auto-Start Services

This directory contains systemd service files for automatically starting the FreqTrade bots on system boot.

## Files

- `freqtrade-bot1.service` - Service file for Bot 1 (LEA-LSTM Strategy)
- `freqtrade-bot2.service` - Service file for Bot 2 (FinAgent Strategy)
- `setup_autostart.sh` - Automated setup script

## Installation

```bash
sudo ./setup_autostart.sh
```

This will:
1. Install systemd service files
2. Enable auto-start on boot
3. Start both bots as services
4. Configure automatic restart on failure

## Manual Installation

```bash
# Copy service files
sudo cp freqtrade-bot1.service /etc/systemd/system/
sudo cp freqtrade-bot2.service /etc/systemd/system/

# Set permissions
sudo chmod 644 /etc/systemd/system/freqtrade-bot*.service

# Reload systemd
sudo systemctl daemon-reload

# Enable and start services
sudo systemctl enable freqtrade-bot1.service
sudo systemctl enable freqtrade-bot2.service
sudo systemctl start freqtrade-bot1.service
sudo systemctl start freqtrade-bot2.service
```

## Management Commands

```bash
# Check status
sudo systemctl status freqtrade-bot1
sudo systemctl status freqtrade-bot2

# Start/stop
sudo systemctl start freqtrade-bot1
sudo systemctl stop freqtrade-bot1
sudo systemctl restart freqtrade-bot1

# Enable/disable auto-start
sudo systemctl enable freqtrade-bot1
sudo systemctl disable freqtrade-bot1

# View logs
sudo journalctl -u freqtrade-bot1 -f
sudo journalctl -u freqtrade-bot2 -f
```

## Service Details

### Bot 1 (LEA-LSTM Strategy)
- Port: 8080
- Config: user_data/config.json
- Strategy: LeaFreqAIStrategy
- Log: freqtrade.log

### Bot 2 (FinAgent Strategy)
- Port: 8081
- Config: user_data/config_finagent.json
- Strategy: LeaFinAgentStrategy
- Log: freqtrade_finagent.log

## Features

- ✅ Auto-start on system boot
- ✅ Automatic restart on failure
- ✅ Background service operation
- ✅ Systemd log management
- ✅ Survives SSH disconnection
- ✅ Environment variable support from .env file

