# LeahAI v5 — Model Specification

**Spec version:** 1.0
**Parent:** `docs/v5-SPEC.md`
**Status:** SUPERSEDED by v6 (XGBoostRegressor)
**Date:** 2026-06-25

> **v6 note (2026-07-11):** lea_v6 uses `XGBoostRegressor` — a standard FreqAI regression model. The GARCH(1,1) and Markov-switching models described in this spec are not yet deployed. The `_garch_persistence()` method exists in `LeahAI.py` but is not wired into the entry gate.

---

## Model Overview

v5 replaces the single XGBoost gate with two lightweight statistical models and one technical filter, all operating on BTC returns:

```
ENTRY = ALL THREE:
  GARCH(1,1): P(vol_expansion) > threshold  # vol timing
  Markov:     P(expansion_state) > 0.70    # regime persistence
  Technical:  close[pair] > EMA50[pair]     # pair momentum
```

Three independent signals. All must clear. None depends on the other two.

---

## Model 1 — GARCH(1,1) for Volatility Timing

### Purpose
Volatility is autocorrelated. Periods of low vol reliably precede periods of high vol. GARCH(1,1) models this clustering and produces a forward variance forecast. Entry only when the model estimates vol is likely to expand — directional moves follow vol expansion.

### Equation

**Variance recursion:**
```
σ²_t = ω + α · ε²_{t-1} + β · σ²_{t-1}

Where:
  ω  = long-run variance floor (estimated from data)
  α  = ARCH coefficient — sensitivity to past shock (ε²_{t-1})
  β  = GARCH coefficient — variance persistence
  ε² = squared return innovation (residual from mean return)
```

**Forecast:** σ²_{t+1} = ω + (α + β) · σ²_t

**Expansion probability:**
```
P(vol_expansion) = P(σ²_{t+1} > σ²_t | estimated params)
                 = P(ε²_t > σ²_t | estimated params)   [from recursion]
```

In practice: if α · ε²_{t-1} > 0, vol is trending up. P(vol_expansion) ≈ α · ε²_{t-1} / σ²_t for the next step, or use the ratio of 1-step forecast to current realized variance.

### Parameters to Estimate
- ω, α, β via maximum likelihood on rolling 500-candle BTC return window
- Re-estimate daily or on new candle batch
- Starting values: ω = 0.01 · var(r), α = 0.1, β = 0.85 (standard arch package defaults)

### Threshold
**Empirically calibrated: log(h₁ / σ²_trail) > 0.050** (2026-06-26, BTC 5m, 41,460 candles)

- Spearman IC vs forward vol expansion: 0.374 (p=0.0000) — statistically significant
- Separation: 0.315 (base rate = 47.9%)
- The ratio h₁ / σ²_trail = exp(0.050) ≈ 1.051: GARCH expects 1h vol to exceed ~105% of trailing realized vol
- Recalibrate if BTC market structure changes materially (new exchange listings, regime shift, etc.)

### Implementation
```python
from arch import arch_model
import numpy as np

def estimate_garch(returns: np.ndarray, p=1, q=1):
    """Estimate GARCH(1,1) on BTC return series. Returns model and params."""
    am = arch_model(returns * 100, vol='Garch', p=p, q=q, dist='normal')
    res = am.fit(disp='off', show_warning=False)
    return res

def p_vol_expansion(model_res, latest_return: float) -> float:
    """Probability that next-period variance exceeds current variance."""
    forecast = model_res.forecast(horizon=1)
    next_var = forecast.mean.iloc[-1, 0] / 10000  # scale back
    current_var = model_res.conditional_volatility.iloc[-1]**2 / 10000
    return float(next_var / (current_var + 1e-10))  # ratio, capped

# Entry gate: p_vol_expansion(...) > GARCH_THRESHOLD
```

### Integration with Freqtrade
- Run GARCH estimation in `populate_indicators` on the BTC dataframe before entry logic
- Store `p_vol_expansion` in the dataframe as a custom column
- Gate in `confirm_trade_entry`: `dataframe['p_vol_expansion'].iloc[-1] > GARCH_THRESHOLD`

---

## Model 2 — Markov-Switching for Regime Detection

### Purpose
The v4 hard BTC trend gate (`btc_trend >= 0.002`) fires on single-candle regime flashes. The Markov model learns the persistence of expansion vs contraction from BTC return data and requires the market to be in a *sustained* expansion state before entry.

### Two Hidden States
- **Expansion (E):** Low-variance, directional returns (bull or bear, trending)
- **Contraction (C):** High-variance, mean-reverting returns (chop, noise)

### Transition Matrix
```
         To E    To C
From E [  p_EE,  p_EC ]   p_EE + p_EC = 1
From C [  p_CE,  p_CC ]   p_CE + p_CC = 1
```

**Interpretation:**
- p_EE = probability expansion persists (high = stable regime)
- p_EC = probability regime switches from expansion → contraction
- p_CE = probability regime switches from contraction → expansion
- p_CC = probability contraction persists

### Emission Distributions
- Expansion: N(μ_E, σ²_E) — tight distribution around mean
- Contraction: N(μ_C, σ²_C) — wide distribution, zero mean

### Filtered State Probability
```
P(S_t = E | r_1, ..., r_t) ∝ L(r_t | S_t=E) · Σ P(S_{t-1}) · P(S_t=E | S_{t-1})
```

Updated every candle via forward algorithm (predict → update cycle).

**Entry gate:** P(expansion_state | observed returns) > 0.70

This means: the filtered probability of being in the expansion state must exceed 70% before entry. The model has seen enough evidence to be confident the regime is sustained, not a single-candle flash.

### Viterbi Decoding (for analysis, not gating)
The Viterbi algorithm finds the most probable state sequence:
```
δ_t(j) = b_j(y_t) · max_i [ δ_{t-1}(i) · a_ij ]

Where:
  δ_t(j)    = probability of best path ending in state j at time t
  b_j(y_t)  = emission likelihood of observation y_t given state j
  a_ij      = transition probability i → j
  max_i     = Viterbi picks best predecessor state
```

Most probable state sequence tells us whether expansion was sustained or brief.

### Parameters to Estimate
- Transition matrix: use Hamilton (1989) two-state Markov switching MLE
- Starting values: p_EE = 0.95, p_CC = 0.90 (high persistence, empirically reasonable)
- Update monthly or weekly during dry-run

### Implementation
```python
import numpy as np
from scipy.optimize import minimize

def markov_loglik(params, returns):
    """Negative log-likelihood of two-state Markov switching model."""
    p_EE, p_EC, mu_E, mu_C, sig_E, sig_C = unpack_params(params)
    # Forward algorithm — predict and update filtered state probabilities
    # Returns negative log-likelihood (minimize)
    ...

def fit_markov(returns, init_params=None):
    """Fit two-state Markov switching model via MLE."""
    if init_params is None:
        init_params = [0.95, 0.05, returns.mean(), 0, returns.std(), returns.std()*2]
    res = minimize(markov_loglik, init_params, args=(returns,),
                   bounds=[(0.5,0.99),(0.01,0.5),(None,None),(None,None),(1e-4,None),(1e-4,None)])
    return res.x

def filtered_p_expansion(params, returns) -> np.ndarray:
    """Forward-filtered P(expansion | observed returns) for each time t."""
    p_EE, p_EC, mu_E, mu_C, sig_E, sig_C = params
    # Forward algorithm: predict → update cycle
    # Returns array of P(S_t=E | r_1,...,r_t) for each t
    ...

# Entry gate: filtered_p_expansion(params, btc_returns)[-1] > 0.70
```

### Integration with Freqtrade
- Run filtered P(expansion) update in `populate_indicators` on the BTC dataframe
- Store `p_expansion_state` in the dataframe as a custom column
- Gate in `confirm_trade_entry`: `signal_candle['p_expansion_state'] > 0.70`

---

## Model 3 — Pair Momentum (EMA50)

No ML here — simple technical filter. Entry only if `close[pair] > EMA50[pair]` at signal time.

This is unchanged from v4.3 and confirmed working.

---

## Entry Signal Architecture (Full)

```python
def confirm_trade_entry(self, pair: str, slice: TradingSlice) -> bool:
    """All three gates must clear."""
    signal_candle = slice.trading_indicators

    # Gate 1: GARCH vol expansion probability
    p_vol = signal_candle['p_vol_expansion']

    # Gate 2: Markov filtered expansion probability
    p_exp = signal_candle['p_expansion_state']

    # Gate 3: Pair momentum
    above_ema = signal_candle['close'] > signal_candle['ema_50']

    # All three must pass
    return (p_vol > GARCH_THRESHOLD
            and p_exp > 0.70
            and above_ema)
```

Note: No FreqAI probability gate here. The GARCH/Markov ensemble replaces the XGBoost classifier. This is the architectural change — not an incremental fix to the old model.

---

## Calibration Test (REQUIRED before live capital)

**Trigger:** n=30 closed dry-run trades

**Method:**
```python
def calibration_test(trades: list[TradeRecord]) -> dict:
    """
    Returns {
        'passes': bool,
        'bins': {bin_label: (count, win_rate)},
        'monotonic': bool
    }
    """
    high   = [(t.enter_tag_prob, t.is_win) for t in trades if t.enter_tag_prob > 0.70]
    mid    = [(t.enter_tag_prob, t.is_win) for t in trades
              if 0.60 < t.enter_tag_prob <= 0.70]
    low    = [(t.enter_tag_prob, t.is_win) for t in trades
              if 0.55 < t.enter_tag_prob <= 0.60]

    win_rate = lambda bucket: sum(w for _, w in bucket) / len(bucket) if bucket else None

    wr_high = win_rate(high)
    wr_mid  = win_rate(mid)
    wr_low  = win_rate(low)

    passes    = (wr_high > wr_mid > wr_low)
    monotonic = passes  # same condition, named clearly

    return {
        'passes': passes,
        'monotonic': monotonic,
        'bins': {
            'prob>0.70': (len(high), wr_high),
            '0.60-0.70': (len(mid), wr_mid),
            '0.55-0.60': (len(low), wr_low),
        },
        'sample_size': len(trades),
        'minimum_met': len(trades) >= 30
    }
```

**Pass criteria:** `passes == True` AND `sample_size >= 30`

**If PASSES:** Proceed to live capital with probability-weighted position sizing.

**If FAILS:** HALT. Do not run past n=30. No extensions. Use uniform sizing + flat threshold.

---

## Enforcement

### Hard Stop at n=30

1. **Config flag:** Set `max_trades=30` in the Freqtrade config before starting the dry-run. The bot stops accepting new entries when closed trade count reaches 30.

2. **Kill-switch:** When n=30 is reached (or at any suspicion of a problem):
   ```bash
   bash /home/shad/kill_all_trading.sh
   ```
   This is the ONLY trusted halt command. `docker stop` alone is not sufficient.

3. **Verification before proceeding to live:**
   - Run calibration test on the 30 closed dry-run trades
   - If test fails: archive model, open incident ticket, do not deploy to live
   - If test passes: proceed to live capital sizing discussion

---

## Open Decisions (must resolve before dry-run starts)

| Decision | Options | Recommended | Status |
|----------|---------|-------------|--------|
| GARCH threshold | 0.55 / 0.60 / 0.65 / from historical backtest | 0.60 (starting hypothesis) | OPEN |
| Markov lookback | 24h / 48h / 7d BTC returns | 48h | OPEN |
| GARCH update frequency | Every candle / daily | Daily (in `populate_indicators`) | OPEN |
| Markov update frequency | Every candle / daily | Daily (in `populate_indicators`) | OPEN |
| `enter_tag` format | `prob_X.XXXX` / `garch_X.XXXX_mr_X.XXXX` | `prob_X.XXXX` (unchanged) | RESOLVED |

---

## Reference Files

- Hamilton (1989) regime decoding: `references/fig-hamilton-viterbi.md`
- Viterbi recurrence: `δt(j) = bj(yt) · max[δt-1(i) · aij]`
- v4.3 calibration finding: `references/v4.3-calibration-finding.md`

---

*Architecture follows from what the data proves. Not the other way around.*
