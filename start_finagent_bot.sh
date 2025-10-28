#!/bin/bash
# LEA-FinAgent Bot Startup Script

cd /home/pi/lea-freqai-system

# Kill any existing FinAgent bots
pkill -f "LeaFinAgentStrategy" 2>/dev/null
sleep 2

# Activate environment
source .venv/bin/activate
source .env

# Start bot
nohup freqtrade trade \
  --strategy LeaFinAgentStrategy \
  --freqaimodel PyTorchMLPRegressor \
  --config /home/pi/lea-freqai-system/user_data/config_finagent.json \
  --logfile /home/pi/lea-freqai-system/finagent_bot.log \
  > finagent_startup.log 2>&1 &

echo "LEA-FinAgent Bot started with PID: $!"
echo "Monitor with: tail -f finagent_bot.log"
echo "FreqUI at: http://192.168.50.10:8081"
