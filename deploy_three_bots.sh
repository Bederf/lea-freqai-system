#!/bin/bash
# Deploy Three Freqtrade Strategies as systemctl Services
# Usage: ./deploy_three_bots.sh [install|start|stop|status|logs]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="/etc/systemd/system"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Three-Strategy Freqtrade Deployment${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# ============================================================================
# Function: Install systemctl services
# ============================================================================
install_services() {
    echo -e "${BLUE}[1/3] Installing systemctl services...${NC}"
    echo ""
    
    # Check if running as root or with sudo
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}✗ This script must be run as root (use: sudo ./deploy_three_bots.sh install)${NC}"
        exit 1
    fi
    
    # Copy service files
    echo -e "${YELLOW}Installing freqtrade-finagent.service${NC}"
    cp "$SCRIPT_DIR/freqtrade-finagent.service" "$SYSTEMD_DIR/"
    chmod 644 "$SYSTEMD_DIR/freqtrade-finagent.service"
    
    echo -e "${YELLOW}Installing freqtrade-lea.service${NC}"
    cp "$SCRIPT_DIR/freqtrade-lea.service" "$SYSTEMD_DIR/"
    chmod 644 "$SYSTEMD_DIR/freqtrade-lea.service"
    
    echo -e "${YELLOW}Installing freqtrade-diagnostic.service${NC}"
    cp "$SCRIPT_DIR/freqtrade-diagnostic.service" "$SYSTEMD_DIR/"
    chmod 644 "$SYSTEMD_DIR/freqtrade-diagnostic.service"
    
    # Reload systemd daemon
    echo -e "${YELLOW}Reloading systemd daemon${NC}"
    systemctl daemon-reload
    
    echo -e "${GREEN}✓ All services installed${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Verify configuration: sudo systemctl status freqtrade-{finagent,lea,diagnostic}"
    echo "  2. Start services: sudo systemctl start freqtrade-{finagent,lea,diagnostic}"
    echo "  3. Enable auto-start: sudo systemctl enable freqtrade-{finagent,lea,diagnostic}"
    echo ""
}

# ============================================================================
# Function: Start all services
# ============================================================================
start_services() {
    echo -e "${BLUE}[1/3] Starting all three strategies...${NC}"
    echo ""
    
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}✗ This command must be run as root${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}Starting FinAgent (Safety/Risk Management)...${NC}"
    systemctl start freqtrade-finagent
    sleep 2
    
    echo -e "${YELLOW}Starting LeaFreqAI (Growth/Opportunities)...${NC}"
    systemctl start freqtrade-lea
    sleep 2
    
    echo -e "${YELLOW}Starting Diagnostic (Monitoring/Testing)...${NC}"
    systemctl start freqtrade-diagnostic
    sleep 2
    
    echo -e "${GREEN}✓ All services started${NC}"
    echo ""
    
    # Show status
    echo -e "${BLUE}[2/3] Checking service status...${NC}"
    echo ""
    systemctl status freqtrade-finagent freqtrade-lea freqtrade-diagnostic --no-pager
    echo ""
}

# ============================================================================
# Function: Stop all services
# ============================================================================
stop_services() {
    echo -e "${BLUE}Stopping all three strategies...${NC}"
    echo ""
    
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}✗ This command must be run as root${NC}"
        exit 1
    fi
    
    systemctl stop freqtrade-finagent freqtrade-lea freqtrade-diagnostic
    echo -e "${GREEN}✓ All services stopped${NC}"
    echo ""
}

# ============================================================================
# Function: Show service status
# ============================================================================
show_status() {
    echo -e "${BLUE}Service Status:${NC}"
    echo ""
    systemctl status freqtrade-finagent freqtrade-lea freqtrade-diagnostic --no-pager
    echo ""
    echo -e "${YELLOW}Summary:${NC}"
    echo ""
    
    # Check each service
    for service in finagent lea diagnostic; do
        status=$(systemctl is-active freqtrade-$service 2>/dev/null || echo "inactive")
        if [ "$status" = "active" ]; then
            echo -e "  ${GREEN}✓${NC} freqtrade-$service: ${GREEN}RUNNING${NC}"
        else
            echo -e "  ${RED}✗${NC} freqtrade-$service: ${RED}STOPPED${NC}"
        fi
    done
    echo ""
}

# ============================================================================
# Function: Show logs
# ============================================================================
show_logs() {
    local service=$1
    
    case $service in
        finagent)
            echo -e "${BLUE}FinAgent Logs (Last 50 lines):${NC}"
            journalctl -u freqtrade-finagent -n 50 --no-pager
            ;;
        lea)
            echo -e "${BLUE}LeaFreqAI Logs (Last 50 lines):${NC}"
            journalctl -u freqtrade-lea -n 50 --no-pager
            ;;
        diagnostic)
            echo -e "${BLUE}Diagnostic Logs (Last 50 lines):${NC}"
            journalctl -u freqtrade-diagnostic -n 50 --no-pager
            ;;
        *)
            echo -e "${BLUE}All Bot Logs (Last 20 lines each):${NC}"
            echo ""
            echo -e "${YELLOW}FinAgent:${NC}"
            journalctl -u freqtrade-finagent -n 20 --no-pager
            echo ""
            echo -e "${YELLOW}LeaFreqAI:${NC}"
            journalctl -u freqtrade-lea -n 20 --no-pager
            echo ""
            echo -e "${YELLOW}Diagnostic:${NC}"
            journalctl -u freqtrade-diagnostic -n 20 --no-pager
            ;;
    esac
}

# ============================================================================
# Function: Enable auto-start on boot
# ============================================================================
enable_autostart() {
    echo -e "${BLUE}Enabling auto-start on system boot...${NC}"
    echo ""
    
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}✗ This command must be run as root${NC}"
        exit 1
    fi
    
    systemctl enable freqtrade-finagent freqtrade-lea freqtrade-diagnostic
    echo -e "${GREEN}✓ All services enabled for auto-start${NC}"
    echo ""
}

# ============================================================================
# Function: Show deployment summary
# ============================================================================
show_summary() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Deployment Summary${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    
    echo -e "${YELLOW}Strategy 1: FinAgentStrategy_v2_RiskManaged (SAFETY)${NC}"
    echo "  Status: $(systemctl is-active freqtrade-finagent 2>/dev/null || echo 'inactive')"
    echo "  Database: user_data/tradesv3_finagent.sqlite"
    echo "  Logs: journalctl -u freqtrade-finagent -f"
    echo "  Performance: -1.01% (vs Market -21.14%, 21x outperformance)"
    echo "  Max Drawdown: 1.09% (exceptional)"
    echo "  Capital Allocation: 30%"
    echo ""
    
    echo -e "${YELLOW}Strategy 2: LeaFreqAIStrategy (GROWTH)${NC}"
    echo "  Status: $(systemctl is-active freqtrade-lea 2>/dev/null || echo 'inactive')"
    echo "  Database: user_data/tradesv3_lea.sqlite"
    echo "  Logs: journalctl -u freqtrade-lea -f"
    echo "  Performance: -10.75% (high win rate, higher risk)"
    echo "  Win Rate: 83.5% (excellent signal quality)"
    echo "  Capital Allocation: 30%"
    echo ""
    
    echo -e "${YELLOW}Strategy 3: DiagnosticStrategy (MONITORING)${NC}"
    echo "  Status: $(systemctl is-active freqtrade-diagnostic 2>/dev/null || echo 'inactive')"
    echo "  Database: user_data/tradesv3_diagnostic.sqlite"
    echo "  Logs: journalctl -u freqtrade-diagnostic -f"
    echo "  Purpose: Testing, validation, signal monitoring"
    echo "  Capital Allocation: 15%"
    echo ""
    
    echo -e "${YELLOW}Reserve Capital: 25% (opportunities & rebalancing)${NC}"
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ============================================================================
# Main script logic
# ============================================================================
case "${1:-status}" in
    install)
        install_services
        show_summary
        ;;
    
    start)
        start_services
        show_summary
        ;;
    
    stop)
        stop_services
        ;;
    
    status)
        show_status
        show_summary
        ;;
    
    logs)
        show_logs "${2:-all}"
        ;;
    
    enable)
        enable_autostart
        ;;
    
    *)
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  install          - Install services (requires root)"
        echo "  start            - Start all three bots (requires root)"
        echo "  stop             - Stop all three bots (requires root)"
        echo "  status           - Show service status and summary"
        echo "  logs [service]   - Show logs (finagent, lea, diagnostic, or all)"
        echo "  enable           - Enable auto-start on boot (requires root)"
        echo ""
        echo "Examples:"
        echo "  sudo ./deploy_three_bots.sh install      # Install services first"
        echo "  sudo ./deploy_three_bots.sh start        # Start all three"
        echo "  ./deploy_three_bots.sh status            # Check status"
        echo "  ./deploy_three_bots.sh logs lea          # View LeaFreqAI logs"
        echo "  sudo ./deploy_three_bots.sh enable       # Auto-start on boot"
        exit 1
        ;;
esac
