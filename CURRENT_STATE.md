# Current State

This repository is currently operated as a multi-bot Freqtrade workspace, not as the older single-bot LEA setup described in several 2025 documents.

## Use These Docs First

- `DAILY_SCORECARD.md`
  Daily operating view for the current paper-trading bots: `lea`, `finagent`, `diagnostic`, and `bbrsi`.
- `docs/ARCHITECTURE_CONSOLIDATION.md`
  **LeahAI v4.4 architecture audit — current active system.** Full call chain, component status, bug fixes, and Trust Ladder readiness. Updated 2026-07-17.
- `BOT_RESEARCH_WORKFLOW.md`
  Current backtesting and conservative hyperopt workflow using the live bot configs and current strategy files.
- `docs/systemd-services/README.md`
  Current service installation, restart, logging, and monitoring instructions for the systemd-managed bots.
- `PRODUCTION_STATUS_2026-03-18.md`
  Point-in-time production snapshot for the three primary bots and their service/database layout.

## Current Operational Shape

- Bots: `lea`, `finagent`, `diagnostic`, `bbrsi`
- Services: `freqtrade-lea`, `freqtrade-finagent`, `freqtrade-diagnostic`
- Trade databases: `user_data/tradesv3_*.sqlite`
- Daily report: `scripts/daily_scorecard.py`
- Research runner: `scripts/research_bots.sh`

## Historical Docs

The following files are still useful for background, but they describe earlier LEA strategy iterations and should not be treated as current source of truth for deployment or live parameters:

- `LEA_README.md`
- `LEA_STRATEGY_OPTIMIZATION.md`
- `STOPLOSS_STRATEGY_TESTING.md`
- `CHANGELOG_STRATEGY.md`
- `LEA_PROGRESS.md`
- `START_HERE.md`
- `QUICK_START.md`
- `QUICK_START_DRY_RUN.md`
- `DRY_RUN_GUIDE.md`
- `COMPLETE_SETUP.md`

If a historical document conflicts with the files in "Use These Docs First", prefer the current docs.
