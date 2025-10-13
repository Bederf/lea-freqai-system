#!/bin/bash
# FreqTrade Bot Restart Script
# Gracefully stops and restarts the trading bot

echo "🔄 Restarting FreqTrade Bot..."
echo "================================"

# Stop existing processes
echo "⏹️  Stopping existing FreqTrade processes..."
pkill -9 -f "freqtrade trade"
sleep 2

# Verify processes stopped
if ps aux | grep -v grep | grep "freqtrade trade" > /dev/null; then
    echo "❌ Failed to stop FreqTrade process"
    exit 1
fi
echo "✅ FreqTrade stopped"

# Navigate to project directory
cd /home/pi/lea-freqai-system || exit 1

# Activate virtual environment
source .venv/bin/activate || exit 1

# Start FreqTrade in background
echo "🚀 Starting FreqTrade..."
nohup freqtrade trade \
    --config user_data/config.json \
    --strategy LeaFreqAIStrategy \
    --freqaimodel PyTorchMLPRegressor \
    --logfile freqtrade.log > /dev/null 2>&1 &

NEW_PID=$!
sleep 3

# Verify it started
if ps -p $NEW_PID > /dev/null; then
    echo "✅ FreqTrade started successfully (PID: $NEW_PID)"
    echo ""
    echo "📊 Monitor logs:"
    echo "   tail -f freqtrade.log"
    echo ""
    echo "🌐 API Access:"
    echo "   Local:  http://192.168.50.10:8080"
    echo "   VPN:    http://10.240.89.1:8080"
    echo ""
    echo "🔐 Credentials:"
    echo "   Username: admin"
    echo "   Password: f9l4fHChq8ky6HYY6ZKibw=="
else
    echo "❌ Failed to start FreqTrade"
    echo "Check logs: tail -50 freqtrade.log"
    exit 1
fi
