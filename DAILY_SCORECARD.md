# Daily Scorecard

`scripts/daily_scorecard.py` gives a one-command operating summary for the three paper-trading bots:

- `lea`
- `finagent`
- `diagnostic`

It pulls data from the live trade databases in `user_data/tradesv3_*.sqlite`, reads the latest local `5m` feather candles from `user_data/data/binance`, and uses recent heartbeat lines in each bot log to label the bot as `running`, `stale`, or `unknown`.

## Usage

Run for today:

```bash
scripts/daily_scorecard.py
```

Run for a specific day:

```bash
scripts/daily_scorecard.py --date 2026-03-25
```

Hide per-trade open position details:

```bash
scripts/daily_scorecard.py --no-open-details
```

## What It Shows

For each bot, the script prints:

- heartbeat-based status
- entries today
- exits today
- wins today
- losses today
- open trade count
- realized PnL for the selected day
- unrealized open-trade PnL based on the latest local `5m` close
- cumulative realized PnL

If open trades exist, the script also prints:

- trade id
- pair
- open timestamp
- open rate
- latest local price
- unrealized PnL in BTC and percent

## Interpreting It

Use the scorecard to answer three practical questions before moving any bot toward live capital:

1. Is the bot actually alive?
2. Is the bot producing positive realized PnL over time?
3. Are open positions behaving sensibly instead of sitting stale or churning?

The scorecard is meant to be a daily operating view, not a replacement for deeper trade-by-trade review.
