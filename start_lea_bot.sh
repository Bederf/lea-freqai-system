#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# LEA FreqTrade Bot Startup Script
# ═══════════════════════════════════════════════════════════════
# Safe startup with environment validation and error checking

set -e  # Exit on error

# ───────────────────────────────────────────────────────────────
# Color codes for output
# ───────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ───────────────────────────────────────────────────────────────
# Configuration
# ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="user_data/config.json"
LOG_FILE="freqtrade.log"
PID_FILE="/tmp/freqtrade_lea.pid"

# ───────────────────────────────────────────────────────────────
# Helper Functions
# ───────────────────────────────────────────────────────────────
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# ───────────────────────────────────────────────────────────────
# Step 1: Navigate to FreqTrade directory
# ───────────────────────────────────────────────────────────────
cd "$SCRIPT_DIR" || {
    log_error "Failed to change directory to $SCRIPT_DIR"
    exit 1
}
log_info "Working directory: $(pwd)"

# ───────────────────────────────────────────────────────────────
# Step 2: Stop existing FreqTrade processes
# ───────────────────────────────────────────────────────────────
log_info "Checking for existing FreqTrade processes..."
if pgrep -f "freqtrade trade" > /dev/null; then
    log_warn "Stopping existing FreqTrade processes..."
    pkill -f "freqtrade trade" || true
    sleep 3

    # Force kill if still running
    if pgrep -f "freqtrade trade" > /dev/null; then
        log_warn "Force killing stubborn processes..."
        pkill -9 -f "freqtrade trade" || true
        sleep 2
    fi
fi

# Check if port 8080 is free
if lsof -i :8080 > /dev/null 2>&1; then
    log_warn "Port 8080 is still in use. Attempting to free it..."
    kill -9 $(lsof -t -i :8080) 2>/dev/null || true
    sleep 2
fi

log_success "No conflicting processes found"

# ───────────────────────────────────────────────────────────────
# Step 3: Load environment variables
# ───────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    log_error ".env file not found!"
    log_info "Creating template .env file..."
    log_warn "Please edit .env and add your credentials, then run this script again"
    exit 1
fi

log_info "Loading environment variables from .env..."
set -a
source .env
set +a

# ───────────────────────────────────────────────────────────────
# Step 4: Validate critical environment variables
# ───────────────────────────────────────────────────────────────
log_info "Validating environment variables..."

# For dry-run mode, API keys are optional but helpful for data access
if [ "$DRY_RUN" != "false" ]; then
    log_info "Dry-run mode detected - API keys optional"
else
    # Live trading requires API keys
    if [ -z "$BINANCE_API_KEY" ] || [ "$BINANCE_API_KEY" = "your_binance_api_key_here" ]; then
        log_error "BINANCE_API_KEY not set in .env file!"
        log_warn "For live trading, you must provide valid Binance API credentials"
        exit 1
    fi

    if [ -z "$BINANCE_API_SECRET" ] || [ "$BINANCE_API_SECRET" = "your_binance_api_secret_here" ]; then
        log_error "BINANCE_API_SECRET not set in .env file!"
        exit 1
    fi
fi

# Check Telegram configuration
if [ -z "$TELEGRAM_TOKEN" ] || [ "$TELEGRAM_TOKEN" = "your_telegram_bot_token_here" ]; then
    log_warn "Telegram token not configured"
    log_info "Telegram notifications will be disabled"
    log_info "You can configure Telegram later by editing .env"

    # Ask if user wants to disable Telegram in config
    read -p "Disable Telegram notifications? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Disabling Telegram in config..."
        # Use Python to safely modify JSON
        python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
config['telegram']['enabled'] = False
with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=2)
"
        log_success "Telegram disabled"
    fi
fi

log_success "Environment validation complete"

# ───────────────────────────────────────────────────────────────
# Step 5: Activate virtual environment
# ───────────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    log_error "Virtual environment not found at .venv"
    log_info "Please run: python3 -m venv .venv && source .venv/bin/activate && pip install -e ."
    exit 1
fi

log_info "Activating virtual environment..."
source .venv/bin/activate

# ───────────────────────────────────────────────────────────────
# Step 6: Verify FreqTrade installation
# ───────────────────────────────────────────────────────────────
if ! command -v freqtrade &> /dev/null; then
    log_error "FreqTrade not found in virtual environment"
    log_info "Installing FreqTrade..."
    pip install -e . || {
        log_error "Failed to install FreqTrade"
        exit 1
    }
fi

log_success "FreqTrade installation verified"

# ───────────────────────────────────────────────────────────────
# Step 7: Verify configuration file
# ───────────────────────────────────────────────────────────────
if [ ! -f "$CONFIG_FILE" ]; then
    log_error "Configuration file not found: $CONFIG_FILE"
    exit 1
fi

log_info "Validating configuration file..."
freqtrade show-config --config "$CONFIG_FILE" > /dev/null 2>&1 || {
    log_error "Invalid configuration file"
    log_info "Check $CONFIG_FILE for syntax errors"
    exit 1
}

log_success "Configuration valid"

# ───────────────────────────────────────────────────────────────
# Step 8: Parse startup options
# ───────────────────────────────────────────────────────────────
MODE="dry-run"
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --live)
            MODE="live"
            log_warn "⚠️  LIVE TRADING MODE ENABLED ⚠️"
            read -p "Are you sure you want to trade with real money? (yes/NO): " -r
            if [ "$REPLY" != "yes" ]; then
                log_info "Cancelled. Run without --live flag for dry-run mode"
                exit 0
            fi
            shift
            ;;
        --background|-b)
            BACKGROUND=true
            shift
            ;;
        --verbose|-v)
            EXTRA_ARGS="$EXTRA_ARGS --verbose"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Usage: $0 [--live] [--background] [--verbose]"
            exit 1
            ;;
    esac
done

# ───────────────────────────────────────────────────────────────
# Step 9: Display startup summary
# ───────────────────────────────────────────────────────────────
echo ""
log_info "═══════════════════════════════════════════════════════"
log_info "LEA FreqTrade Bot - Starting"
log_info "═══════════════════════════════════════════════════════"
log_info "Mode:          $MODE"
log_info "Config:        $CONFIG_FILE"
log_info "Strategy:      LeaFreqAIStrategy"
log_info "Log file:      $LOG_FILE"
if [ "$BACKGROUND" = true ]; then
    log_info "Running in:    Background"
else
    log_info "Running in:    Foreground (Ctrl+C to stop)"
fi
log_info "API Server:    http://127.0.0.1:8080"
log_info "═══════════════════════════════════════════════════════"
echo ""

# ───────────────────────────────────────────────────────────────
# Step 10: Start FreqTrade
# ───────────────────────────────────────────────────────────────
FREQTRADE_CMD="freqtrade trade --config $CONFIG_FILE --strategy LeaFreqAIStrategy --freqaimodel LeaTorchLSTM $EXTRA_ARGS"

if [ "$MODE" != "live" ]; then
    FREQTRADE_CMD="$FREQTRADE_CMD --dry-run"
fi

log_info "Starting FreqTrade..."
log_info "Command: $FREQTRADE_CMD"
echo ""

if [ "$BACKGROUND" = true ]; then
    # Start in background
    nohup $FREQTRADE_CMD > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"

    sleep 3

    if ps -p $(cat "$PID_FILE") > /dev/null; then
        log_success "FreqTrade started successfully (PID: $(cat $PID_FILE))"
        log_info "View logs: tail -f $LOG_FILE"
        log_info "Stop bot: pkill -f 'freqtrade trade' or kill $(cat $PID_FILE)"
        log_info "Access UI: http://127.0.0.1:8080"
    else
        log_error "FreqTrade failed to start. Check $LOG_FILE for errors"
        rm -f "$PID_FILE"
        exit 1
    fi
else
    # Start in foreground
    log_info "Bot starting... (Press Ctrl+C to stop)"
    echo ""
    $FREQTRADE_CMD
fi

# ───────────────────────────────────────────────────────────────
# Cleanup on exit (foreground mode)
# ───────────────────────────────────────────────────────────────
cleanup() {
    echo ""
    log_info "Shutting down FreqTrade..."
    rm -f "$PID_FILE"
    log_success "Shutdown complete"
}

trap cleanup EXIT
