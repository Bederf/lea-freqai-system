# LeahAI Deployment Notes

## v6.1 — ACTIVE (2026-07-17)

**Bot:** freqtrade-lea-new (docker, `shad/freqtrade-lea-v5:latest`, v2026.4)
**Strategy:** LeahAI (class LeahAIV5Strategy)
**Model:** LeahAI v4.4 — `leah_v4_4_{PAIR}_xgb_clf.pkl` (XGBClassifier)
**Config:** config_lea.json → `force_v44_model=true`, `dry_run=true`
**Database:** tradesv3_lea_v6.sqlite
**Status:** DRY-RUN — v4.4 is live decision-maker

### What changed (v6 → v6.1, 2026-07-17)

Two bugs identified in architecture audit and fixed:

**Bug 1 — `custom_stake_amount` read wrong column**
- Read `dataframe["1"]` (FreqAI column, never written by v4.4) instead of `&-target` (v4.4 probability)
- All positions were uniform size — probability-based stake sizing completely bypassed
- Fix: Changed to read `&-target` (line 1097)

**Bug 2 — `_write_snapshot` used host bind-mount path**
- `self.user_data_dir` resolves to `/home/shad/.../user_data` (host path) inside Docker
- Container has no `/home/shad/` → writes silently failed → `trade_snapshots_v6.jsonl` stopped at July 11
- Fix: Hardcoded `/freqtrade/user_data/logs/trade_snapshots_v6.jsonl` (line 996)

### Architecture note: "shadow mode" label is wrong

The descriptor "shadow mode" was a misnomer. With `force_v44_model=true`:
- `_apply_v44_prediction()` overwrites `&-target` AFTER FreqAI.predict() runs
- `populate_entry_trend()` and `confirm_trade_entry()` read v4.4's overwritten value
- **v4.4 is the sole decision authority, not a passive logger**

FreqAI continues retraining in the background (wasteful but harmless) — its outputs are overwritten before any decision is made.

### Snapshot logging

`trade_snapshots_v6.jsonl` now writes to the correct container path. First entry after fix: pending next v4.4 signal.

### Trust Ladder

| Stage | Trades | Gate | Status |
|-------|--------|------|--------|
| L0 | 1 | v4.4 generating | ✅ Trade #16 |
| L1 | 10 | Snapshot verified | ⬜ 1/10 |
| L2 | 25 | Distribution ±5pp | ⬜ 1/25 |
| L3 | 50 | Breakeven | ⬜ 1/50 |

Full architecture: `docs/ARCHITECTURE_CONSOLIDATION.md`

---

## v6 — (superseded by v6.1, 2026-07-17)

**Bot:** freqtrade-lea-v6 (docker, `2026.4`)
**Strategy:** LeahAI
**Model:** `lea_v6` (XGBoostRegressor)
**Config:** config_lea.json → identifier `lea_v6`
**Database:** not yet populated
**Status:** DRY-RUN — entries blocked by bug FOUND & FIXED same day

### Bug: prob=nan — Entry Gate Reading Wrong Column

**Symptom:** All pairs logged `prob=nan vs 0.55, cond1=False` — no entries fired despite bot running.

**Root cause:** Config uses `XGBoostRegressor` (regression), but `LeahAI.predict()` called `BaseClassifierModel.predict()` and entry gate read column `'1'` (probability of class=1 — a classifier concept). Regression models produce a single `&-target` column with continuous values, no probability columns.

**Historic predictions confirmed:**
```
&-target: 0.665711, 0.381306  ← regression values, NOT probabilities
```

**Fix applied (2026-07-11):**
1. `predict()` override — switched `BaseClassifierModel` → `BaseRegressorModel`
2. Entry gate condition 1 — `dataframe["1"]` → `dataframe["&-target"]`
3. Debug logging — same column fix
4. `enter_tag` persistence — same column fix

**Files changed:** `user_data/strategies/LeahAI.py`

**Note:** The v5 spec (docs/v5-SPEC.md) describes a GARCH+Markov ensemble, but lea_v6 is a direct XGBoostRegressor retrain on current data. The `_garch_persistence()` method still exists in `LeahAI.py` but is not yet wired into the entry gate.

---

## v4.3 — OFFICIAL POST-MORTEM

**Date:** 2026-06-25
**Bot:** freqtrade-lea-new (docker, `2026.4_freqai`)
**Strategy:** LeahAI v4.3
**Model:** `leah_v4_3` (archived as `leah_v4_3_FAILED_2026-06-25`)
**Config:** config_lea_v4.json → identifier `leah_v4_3`
**Database:** tradesv3_lea_v2.sqlite
**Status: FAIL — ARCHIVED**

---

## Verdict

**v4.3: FAIL.** Do not go live.

Full-window (n=43–52 depending on cutoff) expectancy negative and trending worse. Never threatened the +$0.10 bar after n=7. Exit engineering (stoploss, time exit) confirmed working correctly throughout.

Entry signal insufficient — both on raw win rate (42–46% against required ~55–70% depending on payoff window) and on calibration (highest-confidence predictions performing worst in the only properly tagged sample).

---

## What Went Wrong

### Finding: Model Overconfidence at High Probability

This is the real finding — larger than the FAIL verdict itself.

**Trades 48 and 49 (June 24):**
- ETH/USDT: prob=0.8503 → **-$2.24 (stop_loss)**
- SOL/USDT: prob=0.7674 → **-$2.35 (stop_loss)**

These are the two highest-confidence signals in the entire tagged sample. They are also the two largest losses.

**Prior observations:**
- Trade 34 (weeks earlier): prob=0.8966 → near-zero loss

Three separate observations across two checkpoints, all saying the same thing: **the model's highest-confidence predictions are not its most reliable ones.**

This is not noise at n=8. The pattern is consistent and getting sharper as the tagged sample grows. The textbook signature of **overfitting to spurious feature combinations** — decisive in training, unreliable live. The v3 logloss divergence (0.59→0.64, model fit noise after iteration 50) points to the same root cause: a model that learned training noise and assigns it high confidence.

**Implication for the threshold fix:** Raising the entry threshold to 0.70 — floated as a cheap fix — would make things worse, not better. A higher threshold filters toward exactly the confidence band that is failing hardest.

---

## Operational Gap: n=50 Boundary Not Enforced

The validation run target was 50 closed trades. The bot kept accepting entries after n=50 closed, resulting in trades 51 and 52 opening while trade 50 was still open. One trade (trade 50, LINK/USDT) remains open at time of shutdown.

**Fix required:** Add a hard stop in the validation tooling — either a config flag to cap max entries, or a manual halt triggered at n=50. This must not recur in v5 validation.

---

## Architecture History

| Version | Result | Key Issue |
|---------|--------|-----------|
| v3 | Logloss divergence at iteration 50 (0.59→0.64) | Model fit noise after iteration 50 |
| v4.1 | FAIL (n=27, -$0.17/trade) | Kill-bar fix applied, entry signal still insufficient |
| v4.3 | FAIL (n=38 closed post-fix, -$0.26/trade full window) | Calibration failure: highest-confidence predictions worst outcomes |

---

## What Worked

- **Exit engineering:** Stoploss and 6h time exit confirmed firing correctly throughout
- **Discipline:** Bot ran cleanly to completion without manual intervention
- **Validation process:** Caught the calibration finding with a properly tagged 8-trade sample

---

## v5 Directive

**Start from the calibration question, not from architecture first.**

The Markov/GARCH rebuild remains the right architectural direction — but before deploying v5 live, the following acceptance test must pass:

> **Monotonic calibration test:** Win rate must increase monotonically with model probability across a properly sized sample. Specifically: P(win | prob > 0.70) must exceed P(win | prob 0.60–0.70), which must exceed P(win | prob 0.55–0.60). If this does not hold, the model's confidence scores cannot be trusted for position sizing or threshold gating.

**Confidence that doesn't track accuracy is worse than no confidence signal at all — it actively misdirects.**

Until calibration is confirmed, v5 should either:
1. Use uniform position sizing with no probability-weighted weighting
2. Operate with a conservative flat threshold that is not derived from model probabilities

---

## Files

- **Archived model:** `user_data/models/leah_v4_3_FAILED_2026-06-25/`
- **Validation logs:** `validation_v4_3_probwatch.log`
- **Database:** `tradesv3_lea_v2.sqlite` (archived snapshot recommended)

---

## Fix Set — v4.3 (Superseded)

These fixes from v4.1/v4.3 are confirmed working and should carry forward to v5 where applicable:

| Fix | Location | Description |
|-----|----------|-------------|
| Entry condition — current row only | Line 481 | `dataframe["1"].iloc[-1] > 0.55` — strictly last row |
| FreqAI predict() override | Lines 326-354 | Bypass broken XGBoostClassifier LabelEncoder chain |
| String column names in predict() | Line 364 | `pred_df.columns = [str(c) for c in pred_df.columns]` |
| Confirm entry — read probability | Line 557 | `signal_candle[1]` — reads col 1, not `&-target` label |
| BTC trend hard gate | Lines 566-567 | Deny entry if `btc_trend < 0.002` |
| 6h negative-profit time exit | Lines 527-528 | Hard exit after 360 min if unrealized P&L < 0 |
| Confirm exit — read probability | Line 607 | Same column fix for exit path |

**v6 fix (2026-07-11):**

| Fix | Location | Description |
|-----|----------|-------------|
| Regression predict() override | Lines 339-352 | Switch BaseClassifierModel → BaseRegressorModel (config uses XGBoostRegressor) |
| Entry gate — read `&-target` | Line 467 | Regression value from `dataframe["&-target"]`, not column `'1'` |
| Debug/logging column fix | Lines 497, 502 | Same `&-target` fix for logging |
| enter_tag column fix | Lines 490-494 | Same `&-target` fix for trade tags |

Container-internal patches (Freqtrade v2026.4 upstream bugs):

| File | Fix | Notes |
|------|-----|-------|
| `data_drawer.py` lines 304-305 | `pd.to_datetime(..., utc=True)` | Pandas 2.x compatibility |
| `data_drawer.py` lines 368-369 | `labels_std` existence guard | Prevents KeyError |
| `XGBoostClassifier.py` lines 79-81 | Bypass label encode/rename | Removes LabelEncoder chain |
| `data_kitchen.py` line 904 | `is_string_dtype` guard | Prevents int/str mismatch |
| `freqai_interface.py` line 928 | `pd.to_datetime(..., utc=True)` | Pandas 2.x compatibility |

---

---

## Open Incident — 2026-06-25

**An unexplained process briefly appeared in ps output on 2026-06-25, pointing to a nonexistent binary path (`/home/ftuser/.local/bin/freqtrade`). Origin untraced. The process did not write to the trades database. All 52 trade records in `tradesv3_lea_v2.sqlite` are confirmed `LeahAIStrategy` (Docker bot, sole writer). The Docker restart policy was corrected to `no` to prevent auto-restart. System monitored for recurrence.**

---

* Six weeks. Four architectures. One honestly earned negative result with full attribution. *
