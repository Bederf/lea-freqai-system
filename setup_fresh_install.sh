#!/bin/bash
# LEA FreqAI System - Fresh Installation Script
# For Banana Pi / ARM64 devices running Debian/Ubuntu

set -e  # Exit on error

echo "==========================================="
echo "LEA FreqAI System - Fresh Installation"
echo "==========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}Error: Do not run this script as root${NC}"
   exit 1
fi

echo -e "${GREEN}Step 1: Updating system packages...${NC}"
sudo apt-get update
sudo apt-get upgrade -y

echo ""
echo -e "${GREEN}Step 2: Installing system dependencies...${NC}"
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    git curl wget \
    build-essential libssl-dev libffi-dev \
    libblas-dev liblapack-dev gfortran \
    libhdf5-dev libatlas-base-dev \
    libfreetype6-dev libpng-dev \
    pkg-config

echo ""
echo -e "${GREEN}Step 3: Installing TA-Lib...${NC}"
if [ ! -f /usr/lib/libta_lib.so ]; then
    cd /tmp
    wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
    tar -xzf ta-lib-0.4.0-src.tar.gz
    cd ta-lib
    ./configure --prefix=/usr
    make
    sudo make install
    sudo ldconfig
    cd -
    echo -e "${GREEN}TA-Lib installed successfully${NC}"
else
    echo -e "${YELLOW}TA-Lib already installed, skipping...${NC}"
fi

echo ""
echo -e "${GREEN}Step 4: Setting up Python virtual environment...${NC}"
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "${GREEN}Virtual environment created${NC}"
else
    echo -e "${YELLOW}Virtual environment already exists${NC}"
fi

source .venv/bin/activate

echo ""
echo -e "${GREEN}Step 5: Upgrading pip, wheel, and setuptools...${NC}"
pip install --upgrade pip wheel setuptools

echo ""
echo -e "${GREEN}Step 6: Installing FreqTrade...${NC}"
pip install -e .

echo ""
echo -e "${GREEN}Step 7: Installing FreqAI dependencies...${NC}"
pip install -r requirements-freqai.txt

echo ""
echo -e "${GREEN}Step 8: Installing PyTorch (CPU version for ARM64)...${NC}"
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

echo ""
echo -e "${GREEN}Step 9: Installing TA-Lib Python wrapper...${NC}"
pip install TA-Lib

echo ""
echo -e "${GREEN}Step 10: Setting up configuration files...${NC}"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${YELLOW}Created .env file - Please edit it with your API keys!${NC}"
else
    echo -e "${YELLOW}.env file already exists${NC}"
fi

echo ""
echo -e "${GREEN}Step 11: Creating directories...${NC}"
mkdir -p user_data/data
mkdir -p user_data/models
mkdir -p user_data/logs

echo ""
echo "==========================================="
echo -e "${GREEN}Installation Complete!${NC}"
echo "==========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Configure your API keys:"
echo -e "   ${YELLOW}nano .env${NC}"
echo ""
echo "2. Download market data:"
echo -e "   ${YELLOW}source .venv/bin/activate${NC}"
echo -e "   ${YELLOW}freqtrade download-data --exchange binance --timeframes 5m 15m 1h --pairs BTC/USDT ETH/USDT --days 90${NC}"
echo ""
echo "3. Start the bot (paper trading):"
echo -e "   ${YELLOW}./start_lea_bot.sh${NC}"
echo ""
echo "4. Or run manually:"
echo -e "   ${YELLOW}freqtrade trade --strategy LeaFreqAIStrategy --config user_data/config.json${NC}"
echo ""
echo -e "${YELLOW}⚠️  Important: Always test with dry_run: true first!${NC}"
echo ""
