# Bot Research Workflow

This repo now has two separate jobs:

- operate the current dry-run bots safely
- test the current strategy versions with backtesting and hyperopt before moving anything toward live capital

Use this workflow for the current bots:

- `lea`
- `finagent`
- `diagnostic`
- `bbrsi`

## Why This Exists

The older optimization notes in this repo are useful context, but the live strategies have drifted. Old backtest numbers are not a reliable baseline for the code currently running.

This workflow fixes that by using the live bot configs and the current strategy files.

## Research Runner

Use [research_bots.sh](/home/bederf/lea-freqai-system/scripts/research_bots.sh).

Show the current plan:

```bash
scripts/research_bots.sh plan
```

Run a backtest for one bot:

```bash
scripts/research_bots.sh backtest lea 20260201-20260326
```

Run backtests for all current bots:

```bash
scripts/research_bots.sh backtest all 20260101-20260326 --cache none
```

Run a conservative hyperopt for one bot:

```bash
scripts/research_bots.sh hyperopt bbrsi 20260101-20260326 100
```

Override the default spaces if needed:

```bash
scripts/research_bots.sh hyperopt diagnostic 20260101-20260326 80 roi stoploss
```

Results go under:

```text
user_data/backtest_results/current-bots/<bot>/
```

## Default Hyperopt Spaces

These defaults are intentionally narrow.

- `lea`: `roi`
- `finagent`: `roi`
- `diagnostic`: `roi stoploss`
- `bbrsi`: `roi stoploss`

Reasoning:

- `lea` has custom stale/max-age exits and now uses market exits. Re-optimizing stoploss or trailing immediately would blur operational changes with research changes.
- `finagent` uses `custom_stoploss()`. Start by validating expectancy with the current stop logic before widening the search.
- `diagnostic` is a simpler reference bot, so `roi stoploss` is a clean first pass.
- `bbrsi` is the simplest non-FreqAI bot and the easiest place to run a full optimization loop.

## Recommended Sequence

1. Freeze the current strategy version you want to evaluate.
2. Run a backtest over a recent, meaningful timerange.
3. Compare the backtest with the dry-run scorecard from [DAILY_SCORECARD.md](/home/bederf/lea-freqai-system/DAILY_SCORECARD.md).
4. If the strategy still looks viable, run a conservative hyperopt.
5. Re-run backtesting with the optimized parameters before changing the live dry-run bot.

## Practical Rules

- Do not tune multiple major behaviors at once.
- Do not trust old optimization notes after changing entry or exit logic.
- Do not move a bot toward live capital based only on a few dry-run trades.
- Prefer one stable benchmark timerange across bots so comparisons stay honest.

## Good Starting Timeranges

- recent market check: `20260201-20260326`
- broader sample: `20260101-20260326`

FreqAI bots will run materially slower than `bbrsi`.

## Operational Pairing

Use the research workflow together with the daily operating view:

- research: [BOT_RESEARCH_WORKFLOW.md](/home/bederf/lea-freqai-system/BOT_RESEARCH_WORKFLOW.md)
- operations: [DAILY_SCORECARD.md](/home/bederf/lea-freqai-system/DAILY_SCORECARD.md)

That separation is intentional:

- the scorecard tells you how the live dry-run bots are behaving now
- the research runner tells you whether the current strategy versions deserve further tuning
