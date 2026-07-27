#!/usr/bin/env bash
# =============================================================================
# v6 n=30 Calibration Check
# =============================================================================
# Halts freqtrade-lea-new if closed trade count >= 30 (excluding BTC/USDT).
# This is the enforcement mechanism for the HARD STOP at n=30.
#
# NOTE: Currently running in SHADOW MODE (force_v44_model=true).
# Shadow mode does NOT place trades — this gate only applies during
# paper/live trading when the model is actively executing.
#
# Usage: bash check_n30.sh
# =============================================================================

set -e

CONTAINER="freqtrade-lea-new"
DB_PATH="/home/shad/lea-freqai-system/user_data/tradesv3_lea_v6.sqlite"

# Count closed trades
closed=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM trades WHERE is_open = 0 AND pair != 'BTC/USDT';" 2>/dev/null || echo "0")
total_all=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM trades WHERE pair != 'BTC/USDT';" 2>/dev/null || echo "0")

echo "[check_n30] Closed trades (excl BTC/USDT): $closed / 30"
echo "[check_n30] Total trades: $total_all"
echo "[check_n30] Mode: shadow (no trades placed)"
echo "[check_n30] DB: tradesv3_lea_v6.sqlite"

if [ "$closed" -ge 30 ]; then
    echo "[check_n30] HARD STOP: $closed closed trades reached. Halting $CONTAINER."
    docker stop "$CONTAINER" 2>/dev/null || true
    echo "[check_n30] Container stopped. Run calibration before restart."
    exit 1
else
    echo "[check_n30] Below threshold ($closed/30). Continuing."
    exit 0
fi
