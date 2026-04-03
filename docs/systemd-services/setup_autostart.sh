#!/bin/bash
# Setup auto-start for all LEA FreqAI services

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICES=("freqtrade-lea" "freqtrade-finagent" "freqtrade-diagnostic" "freqtrade-bbrsi")

echo "============================================"
echo "Setting up Auto-Start for LEA FreqAI services"
echo "============================================"
echo ""

echo "1. Installing systemd unit files..."
for service in "${SERVICES[@]}"; do
    sudo cp "$REPO_ROOT/$service.service" "/etc/systemd/system/$service.service"
done
echo "   ✓ Service files copied"

echo ""
echo "2. Setting permissions..."
for service in "${SERVICES[@]}"; do
    sudo chmod 644 "/etc/systemd/system/$service.service"
done
echo "   ✓ Permissions set"

echo ""
echo "3. Reloading systemd daemon..."
sudo systemctl daemon-reload
echo "   ✓ Daemon reloaded"

echo ""
echo "4. Stopping manual bot runs..."
pkill -f "freqtrade trade" || echo "   (No manual bots running)"
sleep 3
echo "   ✓ Manual bots stopped"

echo ""
echo "5. Enabling auto-start on boot..."
for service in "${SERVICES[@]}"; do
    sudo systemctl enable "$service"
done
echo "   ✓ Auto-start enabled"

echo ""
echo "6. Starting bot services..."
for service in "${SERVICES[@]}"; do
    sudo systemctl start "$service"
    sleep 3
done
echo "   ✓ Services started"

echo ""
echo "============================================"
echo "Status Check"
echo "============================================"
echo ""

for service in "${SERVICES[@]}"; do
    echo "$service:"
    sudo systemctl status "$service" --no-pager -l | head -n 15
    echo ""
done

echo "============================================"
echo "✅ Auto-start setup complete!"
echo "============================================"
echo ""
echo "All services will now start automatically on system boot."
echo ""
echo "Useful commands:"
echo "  sudo systemctl status freqtrade-lea"
echo "  sudo systemctl status freqtrade-finagent"
echo "  sudo systemctl status freqtrade-diagnostic"
echo "  sudo systemctl status freqtrade-bbrsi"
echo "  sudo systemctl restart freqtrade-lea"
echo "  sudo systemctl restart freqtrade-finagent"
echo "  sudo systemctl restart freqtrade-diagnostic"
echo "  sudo systemctl restart freqtrade-bbrsi"
echo "  sudo systemctl disable freqtrade-lea"
echo "  sudo systemctl disable freqtrade-finagent"
echo "  sudo systemctl disable freqtrade-diagnostic"
echo "  sudo systemctl disable freqtrade-bbrsi"
echo ""
echo "View logs:"
echo "  sudo journalctl -f -u freqtrade-lea"
echo "  sudo journalctl -f -u freqtrade-finagent"
echo "  sudo journalctl -f -u freqtrade-diagnostic"
echo "  sudo journalctl -f -u freqtrade-bbrsi"
echo "  tail -f $REPO_ROOT/logs/freqtrade_lea.log"
echo "  tail -f $REPO_ROOT/logs/finagent.log"
echo "  tail -f $REPO_ROOT/logs/freqtrade_diagnostic.log"
echo "  tail -f $REPO_ROOT/logs/freqtrade_bbrsi.log"
echo ""
