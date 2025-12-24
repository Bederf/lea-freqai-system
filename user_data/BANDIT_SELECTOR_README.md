# Contextual Bandit Strategy Selector

**Freqtrade-native implementation of multi-strategy selection using contextual bandits**

This system automatically selects the best trading strategy based on market context, learning from real trade outcomes over time.

---

## What This Is

A **meta-strategy** that chooses between two sub-strategies:

- **LeaFreqAIStrategy**: Conservative (tight stops, quick exits, high confidence threshold)
- **HybridAIStrategy**: Aggressive (wider stops, patient exits, lower threshold)

Instead of picking one strategy and hoping it works in all conditions, the bandit selector:

1. Observes market **context** (volatility, trend, time of day)
2. Selects the strategy with the **best historical performance** in that context
3. Executes trades using that strategy's logic
4. **Learns** from outcomes to improve future selections

---

## How It Works

### Live Loop (Freqtrade)

```
For each trading opportunity:
  ├─ Extract context (volatility, trend, time)
  ├─ Load Q-values from bandit_selector.json
  ├─ Select strategy (90% best Q-value, 10% random exploration)
  ├─ Apply selected strategy's entry/exit logic
  └─ Log selection + context for offline learning
```

### Offline Learning Loop (Meta-Learner)

```
After trades close (run daily):
  ├─ Load closed trades from Freqtrade DB
  ├─ Extract context at entry time
  ├─ Compute reward (risk-adjusted PnL)
  ├─ Update Q-values: Q(context, strategy) ← Q + α[R - Q]
  └─ Save updated bandit_selector.json
```

**No live RL training. No LLMs. Just counting wins per context.**

---

## Installation & Setup

### 1. Files Created

- `user_data/strategies/BanditMetaStrategy.py` - Meta-strategy wrapper
- `user_data/meta_learner.py` - Offline Q-value updater
- `user_data/bandit_selector.json` - Q-value storage
- `user_data/update_bandit.sh` - Automation script

### 2. Update Freqtrade Config

Edit `config_lea_dryrun.json` (or your live config):

```json
{
  "strategy": "BanditMetaStrategy",
  "freqaimodel": "XGBoostRegressor",
  ...
}
```

The BanditMetaStrategy uses the **same FreqAI model** as your existing strategies. It only differs in which entry/exit logic is applied.

### 3. Initial Training (Cold Start)

The bandit starts with **no knowledge** (empty Q-values). You need initial trades to learn from.

**Option A: Use existing trade history**

If you already have trades from LeaFreqAIStrategy or HybridAIStrategy:

```bash
python user_data/meta_learner.py
```

This will process all closed trades and initialize Q-values.

**Option B: Run in exploration mode**

For the first 50-100 trades, the bandit will explore randomly (50% LEA, 50% Hybrid) due to epsilon-greedy. This builds initial Q-values.

To increase exploration during cold start, edit `bandit_selector.json`:

```json
{
  "epsilon": 0.5,  // 50% exploration (change to 0.1 after 100 trades)
  ...
}
```

---

## Usage

### Running Live Trades

```bash
# Dry-run (recommended first)
freqtrade trade --config config_lea_dryrun.json

# Live trading (after dry-run validation)
freqtrade trade --config config_lea_live.json
```

The BanditMetaStrategy will:
- Select LEA or Hybrid based on current context
- Tag each trade with strategy + context (visible in `enter_tag`)
- Log selections to `user_data/bandit_selections.jsonl`

### Updating Q-Values (Learning)

Run this **daily** or after every 10-20 trades:

```bash
./user_data/update_bandit.sh
```

Or manually:

```bash
python user_data/meta_learner.py
```

**What it does**:
- Reads closed trades from `user_data/tradesv3.sqlite`
- Extracts context from each trade
- Computes reward (optimized for consistent small wins)
- Updates Q-values incrementally
- Saves to `bandit_selector.json`

### Monitoring

**1. View Q-values**

```bash
python user_data/meta_learner.py
```

Output shows Q-values per context:

```
📊 vol_low_trend_up_hour_day (45 trades)
------------------------------------------------------------
  ⭐ LeaFreqAIStrategy          | Q=+0.0120 | N=  28 | Avg=+0.0145
     HybridAIStrategy          | Q=+0.0080 | N=  17 | Avg=+0.0095

📊 vol_high_trend_down_hour_evening (12 trades)
------------------------------------------------------------
  ⭐ HybridAIStrategy          | Q=+0.0020 | N=   8 | Avg=+0.0030
     LeaFreqAIStrategy          | Q=-0.0050 | N=   4 | Avg=-0.0085
```

**Interpretation**:
- ⭐ = Best strategy for this context (will be selected 90% of time)
- **Q** = Expected reward (higher is better)
- **N** = Number of trades observed
- **Avg** = Average reward per trade

**2. View selection log**

```bash
tail -n 20 user_data/bandit_selections.jsonl
```

Shows which strategy was selected for each context.

**3. View update history**

```bash
cat user_data/bandit_updates.log
```

---

## Context Dimensions

The bandit uses **3 context dimensions** with **27 total contexts**:

### 1. Market Volatility (from BTC)
- **low**: σ < 2% (stable market)
- **med**: 2% ≤ σ ≤ 5% (normal market)
- **high**: σ > 5% (volatile market)

### 2. Pair Trend (from EMA50)
- **down**: Price < EMA50 - 2%
- **flat**: Within ±2% of EMA50
- **up**: Price > EMA50 + 2%

### 3. Time of Day
- **morning**: 00:00 - 07:59 UTC
- **day**: 08:00 - 15:59 UTC
- **evening**: 16:00 - 23:59 UTC

**Example context**: `vol_med_trend_up_hour_day`
- Medium volatility
- Uptrend
- Daytime trading

---

## Reward Function

**Optimized for: Consistent small wins**

```python
def compute_reward(trade):
    profit = trade["profit_ratio"]
    duration_minutes = trade["duration"]

    # Cap profit at 2% (don't reward risky moonshots)
    capped_profit = min(profit, 0.02)
    reward = capped_profit

    # PENALTY 1: Losses hurt 3x
    if profit < 0:
        reward = profit * 3  # -2% → -6% reward

    # PENALTY 2: Long holds (>1.5h on 5m)
    if duration_minutes > 90:
        reward -= 0.01

    # BONUS 1: Quick wins (<1h)
    if profit > 0.005 and duration_minutes < 60:
        reward *= 1.5

    # BONUS 2: Sweet spot (0.5-2% profit)
    if 0.005 <= profit <= 0.02:
        reward += 0.002

    return reward
```

**Example outcomes**:
- +1% in 30 min → **+0.017** (best case)
- +3% in 2 hours → **+0.01** (capped, penalized for duration)
- -2% stop loss → **-0.06** (heavily punished)
- +0.5% in 3 hours → **-0.003** (too slow, penalized)

This makes the bandit **prefer frequent small wins over infrequent big wins**.

---

## Tuning Parameters

### Exploration Rate (epsilon)

Controls exploration vs exploitation tradeoff.

Edit `user_data/bandit_selector.json`:

```json
{
  "epsilon": 0.1,  // 10% random exploration (default)
  ...
}
```

**Recommendations**:
- **Cold start** (< 50 trades): `epsilon = 0.5` (high exploration)
- **Learning** (50-200 trades): `epsilon = 0.2` (moderate exploration)
- **Mature** (> 200 trades): `epsilon = 0.1` (low exploration)

### Learning Rate (alpha)

Controls how quickly Q-values adapt to new data.

Edit `user_data/meta_learner.py` (or pass as CLI arg):

```python
learner = ContextualBanditLearner(alpha=0.1)
```

**Recommendations**:
- **Stable markets**: `alpha = 0.1` (slower adaptation, default)
- **Volatile/changing markets**: `alpha = 0.3` (faster adaptation)

### Reward Function

To change optimization goals, edit `compute_reward()` in `user_data/meta_learner.py`:

**Current**: Consistent small wins
**Alternative A**: Max profit (remove capping, reduce loss penalty)
**Alternative B**: Avoid drawdowns (increase loss penalty to 5x)

---

## Automation (Cron Jobs)

### Daily Update (Recommended)

```bash
# Add to crontab
0 0 * * * /home/user/lea-freqai-system/user_data/update_bandit.sh >> /home/user/bandit_cron.log 2>&1
```

Runs at midnight UTC daily.

### Continuous Update (Advanced)

```bash
# Update every hour if new trades exist
0 * * * * /home/user/lea-freqai-system/user_data/update_bandit.sh >> /home/user/bandit_cron.log 2>&1
```

---

## Expected Behavior

### Phase 1: Exploration (First 50 trades)

- Both strategies selected ~50/50 (random exploration)
- Q-values initialized from outcomes
- High variance in selections
- **Purpose**: Gather data across all contexts

### Phase 2: Learning (50-200 trades)

- Patterns emerge in Q-values
- Best strategy per context becomes clear
- Selections become more consistent
- **Purpose**: Build confidence in Q-values

### Phase 3: Exploitation (200+ trades)

- 90% of time: select best strategy per context
- 10% of time: explore (adapt to regime changes)
- Q-values stabilize
- **Purpose**: Maximize returns using learned policy

---

## Troubleshooting

### No Q-values after running meta_learner

**Cause**: Trade metadata doesn't contain strategy/context info.

**Fix**: Ensure you're running `BanditMetaStrategy`, which tags trades with context.

Check `enter_tag` in trades DB:
```bash
sqlite3 user_data/tradesv3.sqlite "SELECT pair, enter_tag, profit_ratio FROM trades WHERE is_open=0 LIMIT 5;"
```

Should see tags like: `lea_bandit_ctx_vol_low_trend_up_hour_day`

### Bandit always selects the same strategy

**Cause**: Insufficient exploration or one strategy dominates all contexts.

**Fix**:
1. Increase epsilon: `"epsilon": 0.2` in `bandit_selector.json`
2. Check Q-values: Is one strategy winning everywhere?
3. If yes, the bandit is working correctly (one strategy is genuinely better)

### Trades not matching expected strategy

**Cause**: Freqtrade not reloading updated config.

**Fix**: Restart Freqtrade after running `update_bandit.sh`:
```bash
# Dry-run
freqtrade trade --config config_lea_dryrun.json
```

Freqtrade loads `bandit_selector.json` on startup.

---

## Limitations & Caveats

### 1. Cold Start Problem

With no prior trades, the bandit has no knowledge. You need **at least 10-20 trades per context** for reliable Q-values.

**Solution**: Start with high exploration (`epsilon = 0.5`) for first 100 trades.

### 2. Context Reconstruction

Currently, context is reconstructed from trade outcomes (volatility inferred from profit magnitude). This is imperfect.

**Better approach** (TODO): Store actual market data at trade entry time, then extract true context.

### 3. Strategy Switching Overhead

Freqtrade can only run one strategy at a time. The bandit switches logic internally, but both strategies must use the **same FreqAI model**.

**This is fine**: Both LEA and Hybrid use XGBoostRegressor with same features. They differ only in entry/exit thresholds.

### 4. Not a Replacement for Risk Management

The bandit selects strategies, but each strategy still has its own stoploss, ROI, etc.

**The bandit does NOT**:
- Override stoploss
- Change position sizing (unless strategy has custom_stake_amount)
- Guarantee profits

It only chooses which strategy logic to apply.

---

## Advanced: Multi-Model Support (Future)

Currently, both strategies use the same FreqAI model (`XGBoostRegressor`).

**Future extension**: Train separate models per strategy:

```json
// config_lea.json
{
  "strategy": "LeaFreqAIStrategy",
  "freqaimodel": "XGBoostRegressor",
  "freqai": {
    "identifier": "lea_model"
  }
}

// config_hybrid.json
{
  "strategy": "HybridAIStrategy",
  "freqaimodel": "CatboostRegressor",
  "freqai": {
    "identifier": "hybrid_model"
  }
}
```

Then run both in separate Freqtrade instances, and use an external meta-controller to route pairs.

**For now**: Single-model bandit is simpler and works well.

---

## FAQ

### Q: Does this use PPO or reinforcement learning?

**No.** This is a **contextual bandit**, which is simpler than RL:
- No state transitions
- No multi-step lookahead
- Just: context → action → reward

It's closer to A/B testing with context.

### Q: Can I add more strategies?

**Yes.** Edit `BanditMetaStrategy.py`:

1. Add new strategy import
2. Add new selection branch in `select_strategy()`
3. Add new entry/exit logic methods
4. Update `meta_learner.py` to recognize new strategy name

### Q: Can I add more context dimensions?

**Yes.** Edit `get_context()` in `BanditMetaStrategy.py`:

Example: Add "BTC dominance":
```python
btc_dom = get_btc_dominance()
dom_regime = "low" if btc_dom < 40 else ("high" if btc_dom > 60 else "med")
context = f"vol_{vol}_trend_{trend}_hour_{time}_dom_{dom}"
```

**Warning**: More dimensions = more contexts = more data needed.

27 contexts (current) is a sweet spot for 5m trading with 3 pairs.

### Q: How do I reset Q-values?

Delete `bandit_selector.json` and restart:

```bash
rm user_data/bandit_selector.json
cp user_data/bandit_selector.json.bak user_data/bandit_selector.json  # Or restore from backup
```

Or manually edit to reset specific contexts.

---

## References

**Paper**: "Contextual Bandits for Multi-Strategy Trading" (fictional, but this is the concept)

**Real papers**:
- Auer et al. (2002) - "Finite-time Analysis of the Multiarmed Bandit Problem"
- Langford & Zhang (2008) - "The Epoch-Greedy Algorithm for Contextual Multi-armed Bandits"

**Freqtrade docs**:
- https://www.freqtrade.io/en/stable/strategy-customization/
- https://www.freqtrade.io/en/stable/freqai/

---

## Support

Issues? Questions?

1. Check logs: `tail -f user_data/logs/freqtrade.log`
2. Verify Q-values: `python user_data/meta_learner.py`
3. Check trade tags: `sqlite3 user_data/tradesv3.sqlite "SELECT enter_tag FROM trades LIMIT 10;"`

If stuck, review this README and the inline code comments.

---

**Good luck. Trade safe. Let the bandit learn.**
