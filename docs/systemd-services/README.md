# Systemd Services for LEA FreqAI Bots

This directory now stores the unit files and helper scripts that keep the current LEA FreqAI bots running as services on every boot.

## Included unit files
- `freqtrade-lea.service` — LEA FreqAI strategy (growth/opportunity focus, port 8080, `user_data/config.json`)
- `freqtrade-finagent.service` — FinAgent strategy (safety/risk management focus, port 8081, `user_data/config_finagent.json`)
- `freqtrade-diagnostic.service` — Diagnostic/monitoring strategy that keeps an eye on data quality and health metrics

Each unit lives at the repository root so you can copy it straight to `/etc/systemd/system/` and keep version control on every change.

## Installation

```bash
sudo ./docs/systemd-services/setup_autostart.sh
```

The script copies each unit to `/etc/systemd/system`, reloads `systemd`, stops any manual `freqtrade trade` processes, enables the units for boot, starts all three bots, and then dumps the short `systemctl status` output for quick verification.

## Manual Installation

```bash
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
sudo cp "$REPO_ROOT/freqtrade-lea.service" /etc/systemd/system/
sudo cp "$REPO_ROOT/freqtrade-finagent.service" /etc/systemd/system/
sudo cp "$REPO_ROOT/freqtrade-diagnostic.service" /etc/systemd/system/

sudo chmod 644 /etc/systemd/system/freqtrade-*.service
sudo systemctl daemon-reload

sudo systemctl enable freqtrade-lea
sudo systemctl enable freqtrade-finagent
sudo systemctl enable freqtrade-diagnostic

sudo systemctl start freqtrade-lea
sudo systemctl start freqtrade-finagent
sudo systemctl start freqtrade-diagnostic
```

## Common Management Commands

```bash
sudo systemctl status freqtrade-lea
sudo systemctl status freqtrade-finagent
sudo systemctl status freqtrade-diagnostic

sudo journalctl -u freqtrade-lea -f
sudo journalctl -u freqtrade-finagent -f
sudo journalctl -u freqtrade-diagnostic -f
```

If you need to stop or restart a subset, use the same service names.

## Service Details

| Service | Strategy | Config | Log |
|---------|----------|--------|-----|
| `freqtrade-lea` | LeaFreqAIStrategy (growth/opportunity) | `user_data/config.json` | `logs/freqtrade_lea.log` |
| `freqtrade-finagent` | FinAgentStrategy_v2_RiskManaged | `user_data/config_finagent.json` | `logs/finagent.log` |
| `freqtrade-diagnostic` | DiagnosticStrategy | `user_data/config_diagnostic.json` | `logs/freqtrade_diagnostic.log` |

All services inherit environment variables from `.env` via the `EnvironmentFile` directive and run inside the same virtual environment as local commands.

## Monitoring Tips

- The [`monitor_three_bots.sh`](../monitor_three_bots.sh) dashboard reads the same `user_data/tradesv3_*` databases that the services write to. It now assumes `close_profit_abs` instead of the deprecated `profit_abs` column.
- The [`scripts/daily_scorecard.py`](../../scripts/daily_scorecard.py) report is the quickest daily health check. It summarizes heartbeat status, entries/exits for the day, realized PnL, and unrealized PnL for currently open trades across `lea`, `finagent`, and `diagnostic`.
- The scorecard usage and field definitions are documented in [`DAILY_SCORECARD.md`](../../DAILY_SCORECARD.md).
- Each unit also runs a `freqtrade freqai train` `ExecStartPre` so the persisted model is rebuilt with the current feature/indicator mix before the trading loop begins; training logs land in `logs/*_freqai_train.log`.
- Keep an eye on `journalctl -u freqtrade-diagnostic` for training issues or stuck orders. If the diagnostic bot reports repeated `amount=0` open trades, the `orders` table can be inspected for cancelled buy attempts.
- The diagnostic strategy now logs a gate summary plus block/adjust lines (e.g., `gate_summary pair=UNI/BTC ... allow_trade=yes risk_multiplier=0.35`) so you can see how signal quality influences trade approval and stake sizing before you add any VaR layer.
- When machines lose connectivity, the `Restart=always` policy will bring the services back online; use `systemctl restart` only if a manual recovery is needed.

## Troubleshooting

- `systemctl status` or `journalctl` will show the exact command line, PID, and recent logs for each service.
- Use `tail -f logs/*.log` to watch strategy-specific output.
- If you change `.env`, reload the daemon and restart the relevant services to pick up updated credentials.
