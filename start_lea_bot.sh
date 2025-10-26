#!/bin/bash
# LEA FreqAI Bot Startup Script

cd /home/pi/lea-freqai-system

# Kill any existing bots
killall -9 freqtrade 2>/dev/null
sleep 2

# Activate environment
source .venv/bin/activate
source .env

# Start bot
nohup freqtrade trade \
  --strategy LeaFreqAIStrategy \
  --freqaimodel PyTorchMLPRegressor \
  --config /home/pi/lea-freqai-system/user_data/config.json \
  > lea_bot.log 2>&1 &

echo "LEA Bot started with PID: $!"
echo "Monitor with: tail -f lea_bot.log"
echo "Check status with: ps aux | grep freqtrade"
