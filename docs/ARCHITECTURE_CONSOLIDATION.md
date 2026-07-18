# LeahAI v4.4 — Architecture Consolidation Report

**Date:** 2026-07-17
**Container:** `freqtrade-lea-new` (shad/freqtrade-lea-v5:latest)
**Config:** `dry_run=true`, `force_v44_model=true`
**Strategy:** LeahAI v6.1 (`user_data/strategies/LeahAI.py`)
**Status:** 🟡 ACTIVE — Bugs fixed, snapshot logging re-enabled, paper run in progress

---

## 1. What Was Done

Two bugs were identified and fixed in `LeahAI.py`:

### Bug 1 — `custom_stake_amount` read wrong column (FIXED)

**Problem:** Line 1097 read `dataframe["1"]` (FreqAI's internal column) instead of `&-target` (v4.4's probability column). Since v4.4 never writes to `"1"`, probability-based stake sizing was always bypassed — all positions were uniform size regardless of confidence.

**Fix:** Changed to read `&-target` directly.

```python
# Before (broken):
if "1" not in dataframe.columns:
    return proposed_stake
prob = float(signal_candle["1"])

# After (fixed):
if "&-target" not in dataframe.columns:
    return proposed_stake
prob = float(signal_candle["&-target"])
```

### Bug 2 — `_write_snapshot` used wrong path (FIXED)

**Problem:** `self.user_data_dir` resolves to the host bind-mount path (e.g. `/home/shad/.../user_data`) when running inside Docker, but that path doesn't exist inside the container. Writes silently failed — `trade_snapshots_v6.jsonl` in the container stopped at July 11.

**Fix:** Hardcoded the container's mount point `/freqtrade/user_data/logs/trade_snapshots_v6.jsonl`.

### Enhancement — Snapshot metadata enriched

`_snapshot_meta` now includes `v44_model` and `v44_features` fields for full pipeline traceability.

---

## 2. Final Execution Architecture

```
RAW OHLCV (5m candle)
        │
        ▼
feature_engineering_expand_all()     ← 74 FreqAI features (RUNS → DISCARDED)
feature_engineering_standard()        ← BTC features (cond2 uses %btc_trend)
        │
        ▼
freqai.start()
└── BaseRegressorModel.predict()
    ├── writes: &-target = FreqAI_regression_value       ← OVERWRITTEN by v4.4
    ├── writes: 1       = FreqAI_regression_value       ← NEVER READ
    └── writes: do_predict = 1
        │
        ▼
_apply_v44_prediction()    ← ONLY when force_v44_model=true
├── compute 15 features (numpy, raw OHLCV only)
│     vol_ratio_20, vol_ratio_10, vol_ratio_5, vol_ratio_3
│     vol_ma20, vol_ma10
│     %ret_1, %ret_3
│     candle_body, hl_range
│     lower_shadow, upper_shadow
│     mom_6, atr14, %atr14_rel
├── scaler.transform(feat_df)       ← leah_v4_4_{PAIR}_xgb_clf_scaler.pkl
├── model.predict_proba(X)[:, 1]   ← leah_v4_4_{PAIR}_xgb_clf.pkl
└── OVERWRITE: &-target = v4.4_probability  ← SOLE AUTHORITY
        │
        ▼
populate_entry_trend()
├── cond1: &-target > 0.55              ← v4.4 probability
├── cond2: %btc_trend >= 0.002          ← BTC bull regime
├── cond3: close > ema_50               ← pair in uptrend
├── cond4: do_predict == 1              ← FreqAI quality gate
├── cond5: volume > 0                   ← valid candle
├── cond6: atr14_pct_rank >= 80.0       ← top 20% volatility
├── enter_long = 1 (if all pass)
└── enter_tag = "prob_{v4.4_probability}"
        │
        ▼
confirm_trade_entry()
├── Gate 1: &-target > 0.55             ← v4.4 probability
├── Gate 2: btc_trend >= 0.002
├── Gate 3: close > ema_50
├── _gate_snapshot() → dict (g1–g8, GARCH, all conditions)
├── _write_snapshot() → trade_snapshots_v6.jsonl  ← FIXED: now writes to container path
└── return True
        │
        ▼
Freqtrade Execution Layer
├── MARKET_BUY → Trade recorded in tradesv3_lea_v6.sqlite
├── ROI table   → {0: 5%, 30: 3%, 60: 2%, 120: 1%}
├── custom_exit → time_exit_6h_negative if underwater >6h
└── custom_stoploss → ATR-based dynamic stop
```

---

## 3. Component Status

| Component | Active | Bypassed | Notes |
|---|---|---|---|
| LeahAI v4.4 15-feature XGBClassifier | ✅ | — | Sole decision authority |
| `leah_v4_4_{PAIR}_xgb_clf.pkl` (all 4 pairs) | ✅ | — | BTC/ETH/SOL/LINK loaded |
| `leah_v4_4_{PAIR}_xgb_clf_scaler.pkl` | ✅ | — | Active |
| FreqAI XGBRegressor | ⚠️ | Runs/retrains | Output overwritten; wasteful but not harmful |
| FreqAI 74-feature engineering | ⚠️ | Runs then discarded | Not used in decisions |
| `populate_entry_trend` cond1–cond6 | ✅ | — | v4.4 `&-target` is sole input |
| `confirm_trade_entry` gates | ✅ | — | v4.4 `&-target` |
| `populate_exit_trend` → `exit_long=0` | ✅ | — | ROI table handles exits |
| ROI table | ✅ | — | {0: 5%, 30: 3%, 60: 2%, 120: 1%} |
| `custom_exit` (6h underwater) | ✅ | — | Active |
| `custom_stoploss` (ATR-based) | ✅ | — | Active |
| `custom_stake_amount` | ✅ FIXED | — | Now reads v4.4 probability |
| `_write_snapshot` | ✅ FIXED | — | Now writes to container path |
| `_gate_snapshot` (g1–g8) | ✅ | — | Active in confirm_trade_entry |

---

## 4. Trade Provenance — Current State

### Live DB (as of 2026-07-17)

| ID | Pair | Date | Enter Tag | Prob | Status |
|---|---|---|---|---|---|
| 7–13 | various | Jul 10–11 | legacy FreqAI | various | Closed |
| 14 | LINK/USDT | Jul 14 | prob_0.5700 | 0.570 | Closed — ROI |
| 15 | ETH/USDT | Jul 15 | prob_0.5700 | 0.570 | Closed — time_exit_6h_negative |
| **16** | **LINK/USDT** | **Jul 17 11:45** | **prob_0.6739** | **0.6739** | **Open — v4.4** |

**Trade #16 is the first v4.4-generated trade.** All earlier trades (IDs 7–15) are legacy FreqAI — they predate the Jul 17 container start with `force_v44_model=true`.

### Snapshot Log

`trade_snapshots_v6.jsonl` contains 7 entries (Jul 10–11, all legacy). After Bug #2 was fixed, new entries will be written for every entry and exit.

---

## 5. Active Configuration

```json
{
  "dry_run": true,
  "force_v44_model": true,
  "freqai.identifier": "lea_v6",
  "freqai.freqaimodel": "XGBoostRegressor"
}
```

**Container:** `freqtrade-lea-new` (Up 16h as of 2026-07-17 04:30 UTC)
**Strategy version:** 6.1
**Model files:** `leah_v4_4_{BTC,ETH,SOL,LINK}_xgb_clf.pkl` + `_scaler.pkl`

---

## 6. What Still Needs Doing

| Priority | Item | Status |
|---|---|---|
| HIGH | Restart container to pick up bug fixes | Pending |
| HIGH | Verify `_write_snapshot` fires for next entry | Pending |
| MEDIUM | Disable FreqAI retraining (wasteful, no longer used) | Optional |
| MEDIUM | E001c exit rule degradation investigation | Pending |
| LOW | PAPER_MONITOR checkpoint at 10/25/50 trades | Pending |

---

## 7. Trust Ladder Readiness

**Current paper trading validity:**

| Criterion | Status |
|---|---|
| v4.4 is sole decision authority | ✅ Yes |
| Snapshot logging re-enabled | ✅ Fixed |
| Stake sizing reads v4.4 probability | ✅ Fixed |
| Snapshot fires for entry/exit | ⬜ Pending restart + verification |
| Legacy trades separated from v4.4 trades | ✅ IDs 7–15 legacy, ID 16 v4.4 |
| Checkpoint fires at 10/25/50 trades | ⬜ Not yet reached |

**Conclusion:** Architecture is sound and bugs are fixed. After one restart and one successful snapshot verification, the paper run is valid for Trust Ladder counting.

---

## 8. Files Modified

- `user_data/strategies/LeahAI.py` — Bug fixes + metadata enrichment (lines 996–1010, 1096–1102, 340–343)
