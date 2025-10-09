# LEA FreqAI System - Complete Setup Guide

This guide will help you set up the LEA FreqAI trading system from scratch on a fresh Banana Pi (or similar ARM64 device) with Armbian/Debian.

## System Requirements

- **Hardware**: Banana Pi M64 or similar ARM64 device
- **Storage**: 32GB or 64GB SD card (quality brand: Samsung, SanDisk, Kingston)
- **RAM**: Minimum 2GB
- **OS**: Armbian Bookworm (Debian 12) or Ubuntu 22.04+
- **Python**: 3.9-3.11 (will be installed)

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Bederf/lea-freqai-system.git freqtrade
cd freqtrade

# 2. Run the automated setup
./setup_fresh_install.sh

# 3. Configure your API keys
cp .env.example .env
nano .env  # Add your exchange API keys

# 4. Start the bot
./start_lea_bot.sh
```

## Detailed Installation Steps

### 1. System Preparation

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install system dependencies
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    git curl wget \
    build-essential libssl-dev libffi-dev \
    libblas-dev liblapack-dev gfortran \
    libhdf5-dev libatlas-base-dev \
    libfreetype6-dev libpng-dev

# Install TA-Lib (required for technical analysis)
cd /tmp
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib
./configure --prefix=/usr
make
sudo make install
cd ~
```

### 2. Clone and Setup Repository

```bash
# Clone the repository
cd ~
git clone https://github.com/Bederf/lea-freqai-system.git freqtrade
cd freqtrade

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip wheel setuptools

# Install FreqTrade and dependencies
pip install -e .
pip install -r requirements-freqai.txt

# Install PyTorch (ARM64 optimized)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

### 3. Configure Environment

```bash
# Create .env file from example
cp .env.example .env

# Edit with your credentials
nano .env
```

Required `.env` variables:
```bash
# Exchange API Keys
EXCHANGE_KEY=your_exchange_api_key_here
EXCHANGE_SECRET=your_exchange_secret_here

# Optional: Telegram notifications
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Optional: Advanced features
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
HUGGINGFACE_TOKEN=your_hf_token
```

### 4. Download Historical Data

```bash
# Download data for backtesting and training
freqtrade download-data \
    --exchange binance \
    --timeframes 5m 15m 1h 4h \
    --pairs BTC/USDT ETH/USDT BNB/USDT \
    --days 365
```

### 5. Train the Model (Optional)

```bash
# Train the LEA model with your data
freqtrade freqaimodel-train \
    --strategy LeaFreqAIStrategy \
    --config user_data/config.json \
    --freqaimodel LeaTorchLSTM
```

### 6. Start Trading

```bash
# Paper trading (dry-run mode - recommended first!)
./start_lea_bot.sh

# Or manual start:
freqtrade trade \
    --strategy LeaFreqAIStrategy \
    --config user_data/config.json \
    --freqaimodel LeaTorchLSTM
```

## System Service Setup (Optional)

To run the bot as a system service that starts automatically:

```bash
# Copy service file
sudo cp freqtrade-lea.service /etc/systemd/system/

# Edit paths if needed
sudo nano /etc/systemd/system/freqtrade-lea.service

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable freqtrade-lea
sudo systemctl start freqtrade-lea

# Check status
sudo systemctl status freqtrade-lea

# View logs
sudo journalctl -u freqtrade-lea -f
```

## File Structure

```
freqtrade/
├── .env                          # Your API keys and secrets (gitignored)
├── .env.example                  # Template for .env
├── start_lea_bot.sh             # Quick start script
├── freqtrade-lea.service        # Systemd service file
├── COMPLETE_SETUP.md            # This file
├── QUICK_START.md               # Quick reference guide
├── freqtrade/
│   └── freqai/
│       └── prediction_models/
│           └── LeaTorchLSTM.py  # LEA LSTM model
└── user_data/
    ├── config.json              # Main configuration
    ├── strategies/
    │   └── LeaFreqAIStrategy.py # Trading strategy
    └── data/                    # Downloaded market data
```

## Configuration Files

### Main Config: `user_data/config.json`

Key settings to review:
- `max_open_trades`: Number of simultaneous trades
- `stake_amount`: Amount per trade
- `dry_run`: Set to `true` for paper trading
- `exchange`: Your exchange settings

### Strategy: `user_data/strategies/LeaFreqAIStrategy.py`

The LEA strategy uses:
- Multiple timeframes (5m, 15m, 1h, 4h)
- LSTM neural network for predictions
- Technical indicators (RSI, MACD, Bollinger Bands, etc.)
- Risk management with stop-loss and ROI targets

## Troubleshooting

### Python Package Issues

```bash
# If PyTorch installation fails
pip install torch==2.0.1 --index-url https://download.pytorch.org/whl/cpu

# If TA-Lib issues
sudo ldconfig
pip install TA-Lib
```

### Memory Issues

```bash
# Check available memory
free -h

# Increase swap if needed
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile  # Set CONF_SWAPSIZE=2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### Data Download Fails

```bash
# Use smaller time range
freqtrade download-data --days 30

# Or download specific pairs only
freqtrade download-data --pairs BTC/USDT
```

## Security Notes

1. **Never commit `.env` file** - It contains your API keys
2. **Use API key restrictions** - Limit to trading only, no withdrawals
3. **Start with paper trading** - Test with `dry_run: true` first
4. **Use stop-loss** - Always set protective stop-losses
5. **Monitor regularly** - Check logs and performance daily

## Performance Optimization

### For Banana Pi / ARM64 devices:

```bash
# Use swap file
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Updating the Bot

```bash
cd ~/freqtrade
git pull
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Support & Resources

- **Repository**: https://github.com/Bederf/lea-freqai-system
- **FreqTrade Docs**: https://www.freqtrade.io/
- **Issues**: Report bugs via GitHub Issues

## License

See LICENSE file for details.

---

**⚠️ Trading Risk Warning**: Cryptocurrency trading carries substantial risk. Only trade with funds you can afford to lose. Past performance does not guarantee future results. Always start with paper trading (dry-run mode) before using real funds.
