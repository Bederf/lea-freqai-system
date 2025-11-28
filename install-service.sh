#!/bin/bash

echo "════════════════════════════════════════════════════════════"
echo "Freqtrade Systemctl Service Installation"
echo "════════════════════════════════════════════════════════════"
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
   echo "❌ This script must be run as root (use: sudo ./install-service.sh)"
   exit 1
fi

echo "✅ Installing freqtrade.service..."
cp /tmp/freqtrade.service /etc/systemd/system/freqtrade.service

echo "✅ Reloading systemctl daemon..."
systemctl daemon-reload

echo "✅ Enabling freqtrade service (auto-start on boot)..."
systemctl enable freqtrade

echo
echo "════════════════════════════════════════════════════════════"
echo "✨ Installation Complete!"
echo "════════════════════════════════════════════════════════════"
echo
echo "Available commands:"
echo "  Start:    sudo systemctl start freqtrade"
echo "  Stop:     sudo systemctl stop freqtrade"
echo "  Status:   sudo systemctl status freqtrade"
echo "  Logs:     journalctl -u freqtrade -f"
echo "  Disable:  sudo systemctl disable freqtrade"
echo
echo "Next: Configure alerts (Discord/Telegram/Email)"
echo "════════════════════════════════════════════════════════════"
