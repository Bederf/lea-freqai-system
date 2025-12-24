#!/bin/bash
# Contextual Bandit Selector Update Script
# Run this daily or after every N trades to update Q-values

set -e  # Exit on error

# Navigate to freqtrade directory
cd "$(dirname "$0")/.."

echo "========================================"
echo "Contextual Bandit Selector Update"
echo "========================================"
echo "Started: $(date)"
echo ""

# Check if trades database exists
if [ ! -f "user_data/tradesv3.sqlite" ]; then
    echo "❌ ERROR: No trades database found at user_data/tradesv3.sqlite"
    echo "Run Freqtrade with trades first."
    exit 1
fi

# Check if meta_learner.py exists
if [ ! -f "user_data/meta_learner.py" ]; then
    echo "❌ ERROR: meta_learner.py not found"
    exit 1
fi

# Run the meta learner
echo "Running meta learner..."
python user_data/meta_learner.py "$@"

# Check if successful
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Bandit selector updated successfully"
    echo "Completed: $(date)"
    echo ""

    # Log the update
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Bandit selector updated" >> user_data/bandit_updates.log

    # Optional: Reload strategy if Freqtrade is running
    # (Uncomment if you want automatic reload)
    # if pgrep -f "freqtrade trade" > /dev/null; then
    #     echo "Reloading Freqtrade configuration..."
    #     pkill -SIGHUP -f "freqtrade trade"
    # fi
else
    echo ""
    echo "❌ Meta learner failed"
    exit 1
fi
