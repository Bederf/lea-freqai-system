#!/bin/bash
# FreqTrade Bot Monitoring Script

API_URL="http://192.168.50.10:8080/api/v1"
AUTH="admin:f9l4fHChq8ky6HYY6ZKibw=="

echo "================================================"
echo "  FreqTrade Bot Monitor"
echo "================================================"
echo ""

# Bot Status
echo "🤖 BOT STATUS:"
curl -s "${API_URL}/show_config" -u "${AUTH}" | jq -r '"  State: \(.state)\n  Dry Run: \(.dry_run)\n  Max Trades: \(.max_open_trades)"'
echo ""

# Open Trades
echo "📊 OPEN TRADES:"
TRADES=$(curl -s "${API_URL}/status" -u "${AUTH}")
TRADE_COUNT=$(echo "$TRADES" | jq 'length')
if [ "$TRADE_COUNT" -eq 0 ]; then
    echo "  No open trades"
else
    echo "$TRADES" | jq -r '.[] | "  \(.pair): \(.profit_pct)% profit, Open: \(.open_date)"'
fi
echo ""

# Profit Summary
echo "💰 PROFIT SUMMARY:"
curl -s "${API_URL}/profit" -u "${AUTH}" | jq -r '"  Total Profit: \(.profit_all_coin) USDT (\(.profit_all_percent_mean)%)\n  Today: \(.profit_today_coin) USDT\n  Win Rate: \(.winning_trades)/\(.trade_count) trades"'
echo ""

# Balance
echo "💵 WALLET BALANCE:"
curl -s "${API_URL}/balance" -u "${AUTH}" | jq -r '.currencies[] | select(.currency == "USDT") | "  USDT: \(.free + .used) (Free: \(.free), Used: \(.used))"'
echo ""

# Performance by Pair
echo "📈 PERFORMANCE BY PAIR:"
curl -s "${API_URL}/performance" -u "${AUTH}" | jq -r '.[] | "  \(.pair): \(.profit_pct)% (\(.count) trades)"' | head -5
echo ""

echo "================================================"
echo "Last updated: $(date)"
echo "================================================"
