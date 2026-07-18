# Strategy Status — Updated 2026-07-17

## Active Strategy: LeahAI v6.1

**Container:** `freqtrade-lea-new` (docker, shad/freqtrade-lea-v5:latest)
**Config:** `dry_run=true`, `force_v44_model=true`
**Status:** ACTIVE — v4.4 is live decision-maker, paper trading in progress

---

## v4.4 Architecture

- **Model:** XGBClassifier (15 features, binary: vol expansion)
- **Label:** `ATR[i+12] > ATR[i] × 1.05`
- **Model files:** `leah_v4_4_{BTC,ETH,SOL,LINK}_xgb_clf.pkl` + `_scaler.pkl`
- **Decision path:** v4.4 overwrites `&-target` in `populate_indicators` → `populate_entry_trend` reads it → `confirm_trade_entry` validates → trade
- **FreqAI role:** Continues retraining but output is overwritten by v4.4 — not authoritative

---

## Bugs Fixed (2026-07-17)

1. `custom_stake_amount` read wrong column (`"1"` instead of `"&-target"`) — probability-based sizing always bypassed
2. `_write_snapshot` used host bind-mount path — silently failed in container

Both fixed in `user_data/strategies/LeahAI.py`. Container restart required.

---

## Paper Trading Status

| ID | Pair | Date | Enter Tag | Prob | Status | Source |
|---|---|---|---|---|---|---|
| 7–13 | various | Jul 10–11 | — | — | Closed | Legacy FreqAI |
| 14 | LINK/USDT | Jul 14 | prob_0.5700 | 0.570 | Closed ROI | Legacy FreqAI |
| 15 | ETH/USDT | Jul 15 | prob_0.5700 | 0.570 | Closed time_exit | Legacy FreqAI |
| 16 | LINK/USDT | Jul 17 11:45 | prob_0.6739 | 0.6739 | Open | **v4.4** |

**Trade #16 is the first v4.4 trade.** Container was restarted Jul 17 with `force_v44_model=true`.

---

## Trust Ladder Readiness

- Paper trades needed: 50 (currently 1 v4.4 trade)
- Snapshot logging: Fixed (needs restart + verify)
- Valid for counting: Pending restart + snapshot verification

Full architecture documentation: `docs/ARCHITECTURE_CONSOLIDATION.md`
