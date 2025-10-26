#!/bin/bash
# LEA FreqAI Bot Monitoring Script

echo "=== LEA FreqAI Bot Status Monitor ==="
echo "Date: $(date)"
echo ""

# Check if bot is running
if pgrep -f "freqtrade trade" > /dev/null; then
    echo "✅ Bot Status: RUNNING"
else
    echo "❌ Bot Status: NOT RUNNING"
fi

echo ""
echo "=== Recent Trades ==="
sqlite3 user_data/tradesv3.sqlite "SELECT pair, datetime(open_date, 'localtime') as open_time, ROUND(profit_ratio * 100, 2) as profit_pct, exit_reason FROM trades ORDER BY open_date DESC LIMIT 10;" -header -column 2>/dev/null || echo "No trades yet"

echo ""
echo "=== Trade Summary ==="
sqlite3 user_data/tradesv3.sqlite "SELECT COUNT(*) as total, SUM(CASE WHEN profit_ratio > 0 THEN 1 ELSE 0 END) as wins, ROUND(SUM(profit_ratio) * 100, 2) as total_profit_pct FROM trades WHERE is_open = 0;" -header -column 2>/dev/null || echo "No closed trades yet"

echo ""
echo "=== Current Open Trades ==="
sqlite3 user_data/tradesv3.sqlite "SELECT pair, datetime(open_date, 'localtime') as open_time FROM trades WHERE is_open = 1;" -header -column 2>/dev/null || echo "No open trades"
