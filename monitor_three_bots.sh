#!/bin/bash
# Monitor Three Freqtrade Strategies in Real-Time
# Usage: ./monitor_three_bots.sh [interval]
# Default interval: 5 seconds

INTERVAL=${1:-5}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ============================================================================
# Function: Get bot stats from database
# ============================================================================
get_bot_stats() {
    local db_path=$1
    local bot_name=$2
    
    if [ ! -f "$db_path" ]; then
        echo "DB_NOT_FOUND"
        return
    fi
    
    # Query trade statistics
    local total_trades=$(sqlite3 "$db_path" "SELECT COUNT(*) FROM trades;" 2>/dev/null || echo "0")
    local open_trades=$(sqlite3 "$db_path" "SELECT COUNT(*) FROM trades WHERE is_open=1;" 2>/dev/null || echo "0")
    local wins=$(sqlite3 "$db_path" "SELECT COUNT(*) FROM trades WHERE close_profit_abs > 0 AND is_open=0;" 2>/dev/null || echo "0")
    local losses=$(sqlite3 "$db_path" "SELECT COUNT(*) FROM trades WHERE close_profit_abs < 0 AND is_open=0;" 2>/dev/null || echo "0")
    local total_profit=$(sqlite3 "$db_path" "SELECT COALESCE(SUM(close_profit_abs), 0) FROM trades WHERE is_open=0;" 2>/dev/null || echo "0")
    local avg_profit=$(sqlite3 "$db_path" "SELECT COALESCE(AVG(close_profit_abs), 0) FROM trades WHERE is_open=0;" 2>/dev/null || echo "0")
    local max_loss=$(sqlite3 "$db_path" "SELECT COALESCE(MIN(close_profit_abs), 0) FROM trades WHERE is_open=0;" 2>/dev/null || echo "0")
    
    # Calculate win rate
    local closed_trades=$((wins + losses))
    if [ $closed_trades -gt 0 ]; then
        local win_rate=$(echo "scale=1; $wins * 100 / $closed_trades" | bc)
    else
        local win_rate="0.0"
    fi
    
    # Calculate profit factor
    if [ $losses -gt 0 ]; then
        local positive_sum=$(sqlite3 "$db_path" "SELECT COALESCE(SUM(close_profit_abs), 0) FROM trades WHERE close_profit_abs > 0 AND is_open=0;" 2>/dev/null || echo "0")
        local negative_sum=$(sqlite3 "$db_path" "SELECT COALESCE(ABS(SUM(close_profit_abs)), 0) FROM trades WHERE close_profit_abs < 0 AND is_open=0;" 2>/dev/null || echo "0")
        if [ $negative_sum != "0" ]; then
            local profit_factor=$(echo "scale=2; $positive_sum / $negative_sum" | bc)
        else
            local profit_factor="0.00"
        fi
    else
        local profit_factor="0.00"
    fi
    
    echo "$total_trades|$open_trades|$wins|$losses|$win_rate|$total_profit|$avg_profit|$max_loss|$profit_factor"
}

# ============================================================================
# Function: Get service status
# ============================================================================
get_service_status() {
    local service=$1
    systemctl is-active "$service" 2>/dev/null || echo "unknown"
}

# ============================================================================
# Function: Display dashboard
# ============================================================================
display_dashboard() {
    clear
    
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Freqtrade Three-Strategy Real-Time Monitor${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "Updated: $(date '+%Y-%m-%d %H:%M:%S') | Refresh: ${INTERVAL}s"
    echo ""
    
    # ========================================================================
    # Strategy 1: FinAgent
    # ========================================================================
    local finagent_status=$(get_service_status "freqtrade-finagent")
    local finagent_stats=$(get_bot_stats "$SCRIPT_DIR/user_data/tradesv3_finagent.sqlite" "FinAgent")
    
    if [ "$finagent_status" = "active" ]; then
        echo -e "${GREEN}✓${NC} ${CYAN}FINAGENT (Safety/Risk Management)${NC} ${GREEN}RUNNING${NC}"
    else
        echo -e "${RED}✗${NC} ${CYAN}FINAGENT (Safety/Risk Management)${NC} ${RED}STOPPED${NC}"
    fi
    
    if [ "$finagent_stats" != "DB_NOT_FOUND" ]; then
        IFS='|' read -r total open wins losses wr profit avg max_loss pf <<< "$finagent_stats"
        
        echo -e "  ${YELLOW}Trades:${NC} $total total | $open open | $wins wins | $losses losses"
        echo -e "  ${YELLOW}Performance:${NC} Win Rate: ${wr}% | Profit: ${YELLOW}${profit} BTC${NC} | Avg: ${avg} BTC"
        echo -e "  ${YELLOW}Risk:${NC} Max Loss: ${RED}${max_loss} BTC${NC} | Profit Factor: ${pf}"
    else
        echo -e "  ${YELLOW}No data yet (database not initialized)${NC}"
    fi
    echo ""
    
    # ========================================================================
    # Strategy 2: LeaFreqAI
    # ========================================================================
    local lea_status=$(get_service_status "freqtrade-lea")
    local lea_stats=$(get_bot_stats "$SCRIPT_DIR/user_data/tradesv3_lea.sqlite" "Lea")
    
    if [ "$lea_status" = "active" ]; then
        echo -e "${GREEN}✓${NC} ${CYAN}LEAFREQAI (Growth/Opportunities)${NC} ${GREEN}RUNNING${NC}"
    else
        echo -e "${RED}✗${NC} ${CYAN}LEAFREQAI (Growth/Opportunities)${NC} ${RED}STOPPED${NC}"
    fi
    
    if [ "$lea_stats" != "DB_NOT_FOUND" ]; then
        IFS='|' read -r total open wins losses wr profit avg max_loss pf <<< "$lea_stats"
        
        echo -e "  ${YELLOW}Trades:${NC} $total total | $open open | $wins wins | $losses losses"
        echo -e "  ${YELLOW}Performance:${NC} Win Rate: ${wr}% | Profit: ${YELLOW}${profit} BTC${NC} | Avg: ${avg} BTC"
        echo -e "  ${YELLOW}Risk:${NC} Max Loss: ${RED}${max_loss} BTC${NC} | Profit Factor: ${pf}"
    else
        echo -e "  ${YELLOW}No data yet (database not initialized)${NC}"
    fi
    echo ""
    
    # ========================================================================
    # Strategy 3: Diagnostic
    # ========================================================================
    local diag_status=$(get_service_status "freqtrade-diagnostic")
    local diag_stats=$(get_bot_stats "$SCRIPT_DIR/user_data/tradesv3_diagnostic.sqlite" "Diagnostic")
    
    if [ "$diag_status" = "active" ]; then
        echo -e "${GREEN}✓${NC} ${CYAN}DIAGNOSTIC (Monitoring/Testing)${NC} ${GREEN}RUNNING${NC}"
    else
        echo -e "${RED}✗${NC} ${CYAN}DIAGNOSTIC (Monitoring/Testing)${NC} ${RED}STOPPED${NC}"
    fi
    
    if [ "$diag_stats" != "DB_NOT_FOUND" ]; then
        IFS='|' read -r total open wins losses wr profit avg max_loss pf <<< "$diag_stats"
        
        echo -e "  ${YELLOW}Trades:${NC} $total total | $open open | $wins wins | $losses losses"
        echo -e "  ${YELLOW}Performance:${NC} Win Rate: ${wr}% | Profit: ${YELLOW}${profit} BTC${NC} | Avg: ${avg} BTC"
        echo -e "  ${YELLOW}Risk:${NC} Max Loss: ${RED}${max_loss} BTC${NC} | Profit Factor: ${pf}"
    else
        echo -e "  ${YELLOW}No data yet (database not initialized)${NC}"
    fi
    echo ""
    
    # ========================================================================
    # Summary
    # ========================================================================
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}Quick Actions:${NC}"
    echo "  View Logs:    ./deploy_three_bots.sh logs [finagent|lea|diagnostic]"
    echo "  Start All:    sudo ./deploy_three_bots.sh start"
    echo "  Stop All:     sudo ./deploy_three_bots.sh stop"
    echo "  Full Status:  ./deploy_three_bots.sh status"
    echo ""
    echo -e "${YELLOW}Exit monitor:${NC} Ctrl+C"
    echo ""
}

# ============================================================================
# Main loop
# ============================================================================
while true; do
    display_dashboard
    sleep "$INTERVAL"
done
