#!/bin/bash
# Setup auto-start for both FreqTrade bots

set -e

echo "============================================"
echo "Setting up Auto-Start for FreqTrade Bots"
echo "============================================"
echo ""

# Copy service files
echo "1. Installing systemd service files..."
sudo cp /tmp/freqtrade-bot1.service /etc/systemd/system/
sudo cp /tmp/freqtrade-bot2.service /etc/systemd/system/
echo "   ✓ Service files copied"

# Set permissions
echo ""
echo "2. Setting permissions..."
sudo chmod 644 /etc/systemd/system/freqtrade-bot1.service
sudo chmod 644 /etc/systemd/system/freqtrade-bot2.service
echo "   ✓ Permissions set"

# Reload systemd
echo ""
echo "3. Reloading systemd daemon..."
sudo systemctl daemon-reload
echo "   ✓ Daemon reloaded"

# Stop current manually-run bots
echo ""
echo "4. Stopping manually-run bots..."
pkill -f "freqtrade trade" || echo "   (No manual bots running)"
sleep 3
echo "   ✓ Manual bots stopped"

# Enable services (auto-start on boot)
echo ""
echo "5. Enabling auto-start on boot..."
sudo systemctl enable freqtrade-bot1.service
sudo systemctl enable freqtrade-bot2.service
echo "   ✓ Auto-start enabled"

# Start services
echo ""
echo "6. Starting bot services..."
sudo systemctl start freqtrade-bot1.service
sleep 5
sudo systemctl start freqtrade-bot2.service
sleep 5
echo "   ✓ Bots started"

# Check status
echo ""
echo "============================================"
echo "Status Check"
echo "============================================"
echo ""

echo "Bot 1 (LEA-LSTM):"
sudo systemctl status freqtrade-bot1.service --no-pager -l | head -15

echo ""
echo "Bot 2 (FinAgent):"
sudo systemctl status freqtrade-bot2.service --no-pager -l | head -15

echo ""
echo "============================================"
echo "✅ Auto-start setup complete!"
echo "============================================"
echo ""
echo "Both bots will now start automatically on system boot."
echo ""
echo "Useful commands:"
echo "  sudo systemctl status freqtrade-bot1    # Check Bot 1 status"
echo "  sudo systemctl status freqtrade-bot2    # Check Bot 2 status"
echo "  sudo systemctl stop freqtrade-bot1      # Stop Bot 1"
echo "  sudo systemctl stop freqtrade-bot2      # Stop Bot 2"
echo "  sudo systemctl restart freqtrade-bot1   # Restart Bot 1"
echo "  sudo systemctl restart freqtrade-bot2   # Restart Bot 2"
echo "  sudo systemctl disable freqtrade-bot1   # Disable auto-start Bot 1"
echo "  sudo systemctl disable freqtrade-bot2   # Disable auto-start Bot 2"
echo ""
echo "View logs:"
echo "  sudo journalctl -u freqtrade-bot1 -f   # Bot 1 logs"
echo "  sudo journalctl -u freqtrade-bot2 -f   # Bot 2 logs"
echo "  tail -f /home/pi/lea-freqai-system/freqtrade.log           # Bot 1 file log"
echo "  tail -f /home/pi/lea-freqai-system/freqtrade_finagent.log  # Bot 2 file log"
echo ""

