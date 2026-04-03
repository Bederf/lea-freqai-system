# Documentation Index

**Last Updated:** 2026-03-29

This repo contains a mix of current operational docs and older LEA optimization notes. The older notes are still useful background, but they no longer match the current multi-bot deployment in every detail.

## Read This First

1. `CURRENT_STATE.md`
   Current source-of-truth index for what this repository is now, which docs are current, and which docs are historical.
2. `DAILY_SCORECARD.md`
   Daily operating view for the live paper-trading bots.
3. `BOT_RESEARCH_WORKFLOW.md`
   Current backtesting and hyperopt workflow using the live bot configs and current strategy files.
4. `docs/systemd-services/README.md`
   Current systemd deployment, restart, log, and monitoring instructions.
5. `PRODUCTION_STATUS_2026-03-18.md`
   Production snapshot showing active bots, service names, and database layout.

## Current Docs

| Document | Purpose |
|----------|---------|
| `CURRENT_STATE.md` | Top-level current-state guide and doc routing |
| `DAILY_SCORECARD.md` | Daily health and PnL review for `lea`, `finagent`, `diagnostic`, and `bbrsi` |
| `BOT_RESEARCH_WORKFLOW.md` | Current backtesting and hyperopt workflow |
| `docs/systemd-services/README.md` | Service management, logs, and monitoring |
| `PRODUCTION_STATUS_2026-03-18.md` | Production snapshot and deployment details |

## Historical Docs

These files describe earlier LEA iterations or older deployment assumptions. Keep them for context, but do not treat them as current source of truth when they conflict with the docs above.

| Document | Notes |
|----------|-------|
| `LEA_README.md` | Older LEA overview and parameter narrative |
| `LEA_STRATEGY_OPTIMIZATION.md` | Historical optimization report |
| `STOPLOSS_STRATEGY_TESTING.md` | Historical stoploss test results |
| `CHANGELOG_STRATEGY.md` | Historical LEA code change log |
| `LEA_PROGRESS.md` | Historical implementation log |
| `START_HERE.md` | Older single-service dry-run setup |
| `QUICK_START.md` | Older single-bot quickstart with outdated paths |
| `QUICK_START_DRY_RUN.md` | Older single-service dry-run quickstart |
| `DRY_RUN_GUIDE.md` | Older dry-run guidance with older DB assumptions |
| `COMPLETE_SETUP.md` | Older device-specific setup guide |

## Practical Rule

If a 2025 LEA document conflicts with `CURRENT_STATE.md`, `DAILY_SCORECARD.md`, `BOT_RESEARCH_WORKFLOW.md`, or `docs/systemd-services/README.md`, prefer the current docs.
