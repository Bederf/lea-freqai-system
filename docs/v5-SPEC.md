# LeahAI v5 — Architecture Spec

**Status:** SUPERSEDED by v6.1 (2026-07-17)
**Prerequisite:** Monotonic calibration test must pass before any live capital
**Started:** 2026-06-25

> **v6.1 update (2026-07-17):** LeahAI v4.4 is active — 15-feature XGBClassifier
> predicting vol expansion. `force_v44_model=true` makes it the sole decision
> authority. Two bugs fixed in v6.1: custom_stake_amount wrong column, and
> _write_snapshot path. Full architecture in `docs/ARCHITECTURE_CONSOLIDATION.md`.
> The GARCH/Markov direction from this spec remains a valid future architectural
> improvement but is not yet implemented.

---

## What Happened (v4 Summary)

Six weeks. Four architectures. One honestly earned negative result.

v4.3 FAIL on a 50-trade dry-run:
- Expectancy: -$0.26/trade (full window), trending worse
- Win rate: 42–46% against a ~55–70% requirement depending on payoff ratio
- Calibration failure: highest-confidence predictions (prob=0.85, 0.77) produced the largest losses (stop_loss). This pattern appeared at trade 34 (prob=0.8966, near-zero loss) and now twice more in the n=8 tagged sample.
- Root cause: Model overfits to spurious feature combinations that look decisive in training but aren't predictive live. Confirmed by v3 logloss divergence (0.59→0.64) at iteration 50.
- Exit engineering (stoploss, time exit): working correctly throughout

**The v4.3 finding that changes v5:** The model's confidence scores are not reliable. A model that assigns high probability to its worst losses will actively misdirect position sizing. This is not a threshold problem — raising the threshold filters toward the exact band that fails hardest.

---

## v5 Entry: Three-Gate Ensemble

v5 replaces the single ML gate with three independent model classes, each operating on a different aspect of market structure:

```
ENTRY = ALL OF:
  1. P(vol_expansion | GARCH(1,1))  > threshold    # volatility timing
  2. P(expansion_state | Markov)   > 0.70         # regime persistence
  3. close[pair]                    > EMA50[pair]  # pair momentum
```

**Why three independent model classes:**
- GARCH addresses volatility timing (vol expansion precedes directional moves)
- Markov addresses regime persistence (brief bull flashes vs. sustained expansion)
- Pair momentum addresses directional conviction independent of BTC regime
- Three fundamentally different model types operating on different market features = lower correlated failure mode

**GARCH (volatility timing):**
- GARCH(1,1) models conditional variance of BTC returns
- `P(vol_expansion)` = P(σ²_t+1 > σ²_t | historical returns)
- Entry only when vol is contracting (low vol → high vol expansion likely = directional move incoming)
- Threshold: TBD from historical calibration (see Calibration section)

**Markov-switching (regime persistence):**
- Two hidden states: Expansion (E) and Contraction (C)
- State transition matrix learned from BTC returns
- `P(expansion_state | observed returns)` updated every candle
- Requires P(E) > 0.70 before entry — regime must be stable, not a brief crossover
- Replaces the hard `btc_trend >= 0.002` gate which fires on 1-candle flashes

**Pair momentum (EMA50):**
- No ML — simple technical filter
- Ensures entry is not against the pair's own trend
- Required even in expansion regime if the pair is in a sustained downtrend

---

## Pre-Deployment Acceptance Test: MONOTONIC CALIBRATION (NON-NEGOTIABLE)

**This test must pass on a properly tagged 30+ trade sample before v5 goes live. It is not optional.**

v5 does not use XGBoost — the model dependency was removed in favor of GARCH + Markov. The calibration test now applies to **Markov P(expansion) at entry**: entries tagged with `garch_{x}_pe_{y}_dur_{z}` carry the P(E) value (`y`) at entry. Win rate must increase monotonically with P(E) at entry — higher-regime-confidence trades must outperform lower ones.

**Test:** Sort closed trades into P(E) bins. Win rate must increase monotonically with regime confidence.

```
P(win | P(E) > 0.85) > P(win | P(E) 0.80–0.85) > P(win | P(E) 0.70–0.80)
```

**Why this matters for v5:** v5's edge is regime selection — not directional prediction. If entries fired with P(E)=0.72 perform worse than entries fired with P(E)=0.85, the persistence requirement is correctly filtering brief flashes. If the relationship is flat or inverted, the Markov filter is not adding information and the architecture needs redesign.

**GARCH log_ratio as secondary check:** Also verify that win rate increases with GARCH log_ratio. Higher GARCH log_ratio means stronger vol expansion signal. If it doesn't predict wins, the GARCH gate is not complementary to the Markov gate.

**Sample scope:** Dry-run trades only.

**Enforcement mechanism — HARD STOP at n=30:**

The n=50 boundary existed in prose in v4.3 but had no enforcement. v5 must not repeat this.

Enforcement is implemented as a **pre-session check script** (`check_n30.sh`) plus a **kill-switch script** (`kill_all_trading.sh`) that halts all freqtrade processes and verifies both Docker and native bots are dark:

```bash
# Pre-session check — halts if n=30 closed trades reached
bash check_n30.sh

# Emergency stop — always available
bash kill_all_trading.sh
```

`check_n30.sh` counts closed trades in `tradesv3_lea_v5.sqlite` (excluding BTC/USDT, which is the regime signal pair, not an independent trade test). If count >= 30, it stops the container and exits 1. It should be run before each session start and can also be run as a cron job.

The calibration test executes automatically when the dry-run reaches n=30 closed trades:
- If monotonic calibration PASSES → proceed to live capital with position sizing unchanged (uniform)
- If monotonic calibration FAILS → do NOT proceed; full re-calibration required, not parameter tweaking

There is no discretion here. The test is not a soft guideline — it is a hard gate on proceeding to live capital.

**Minimum sample:** 30 closed trades with `enter_tag` populated (`garch_*_pe_*_dur_*`). No exceptions, no extensions.

---

## Architecture Decisions Still Open

| Decision | Options | Depends On | Status |
|----------|---------|------------|--------|
| GARCH threshold | Historical vol percentile vs. absolute threshold | Calibration run | **RESOLVED** — see below |
| Markov lookback window | 24h / 48h / 7d BTC returns | Regime duration analysis | **RESOLVED** — see below |
| Position sizing | Kelly fraction / fixed fraction / uniform | Calibration result | Uniform until n=30 |
| Entry tagging scheme | prob only / prob + regime state / full feature vec | Implementation | `garch_{:.3f}_pe_{:.2f}_dur_{}` |

---

## Calibrated Parameters (2026-06-26 — BTC 5m, 2026-02-02 to 2026-06-25)

**DO NOT ADJUST post-start without full re-calibration.**

### Gate 1: GARCH Variance Ratio
- **Threshold**: `log(h₁ / σ²_trail) > 0.050`
- **Interpretation**: GARCH 1-step variance forecast must exceed 105% of trailing 1h realized variance
- **Spearman IC**: 0.374 (p=0.0000) — statistically significant rank correlation with forward vol expansion
- **Separation**: 0.315 (base rate vol expansion = 47.9%)
- **Calibration note**: Positive IC confirms GARCH variance ratio carries directional information about future vol in this dataset. Recalibrate if BTC market structure changes significantly.

### Gate 2: Markov Regime Filter
- **Lookback**: 48h / 576 candles (tested: 24h, 48h, 7d — 48h best balance)
- **P(E) threshold**: 0.70
- **Persistence requirement**: P(E) > 0.70 for **≥3 consecutive 5m candles**
- **Why persistence requirement**: Median P(E)>0.70 run was 2 candles (10min) in calibration data — pure threshold does not filter brief flashes
- **48h estimated params** (2026-06-25): p_EE=0.809, p_CC=0.500, expected expansion=26min, expected contraction=10min

### Gate 3: EMA50 Pair Momentum (unchanged from v4)
- **Threshold**: `close[pair] > EMA50[pair]`
- **BTC trend**: `%btc_trend >= 0.002` (close_BTC above EMA50_BTC by ≥0.2%)

### Entry Gate Summary
ALL THREE required simultaneously — no exceptions:
```
Gate 1: log(h₁/σ²_trail) > 0.05   [GARCH — vol timing, daily update]
Gate 2: P(expansion) > 0.70 for ≥3 consecutive candles  [Markov — regime persistence]
Gate 3: close[pair] > EMA50[pair]  [pair momentum]
```

### Position Sizing
- Uniform stake (proposed_stake) until calibration test at n=30

---

## Carry-Forward from v4

Confirmed working fixes that should be preserved in v5:
- `data_drawer.py` pd.to_datetime utc=True fix (Pandas 2.x)
- `data_drawer.py` labels_std existence guard (KeyError prevention)
- `XGBoostClassifier.py` LabelEncoder bypass
- `data_kitchen.py` is_string_dtype guard
- `freqtrade_interface.py` pd.to_datetime utc=True fix
- BTC trend hard gate (until Markov P(expansion) replaces it)
- 6h negative-profit time exit
- String column names in predict()

---

## Files

- Model archive: `user_data/models/leah_v4_3_FAILED_2026-06-25/`
- Post-mortem: `DEPLOYMENT_NOTES.md`
- This spec: `docs/v5-SPEC.md`

---

*Start from calibration. Architecture follows from what the data proves, not the other way around.*
