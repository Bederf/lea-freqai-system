# LeahAI v4.1 Deployment Notes

## Status: VALIDATION IN PROGRESS (2026-06-09)

---

## Fix Set — What's Actually Live

### 1. LeahAI.py (volume-mounted, verified container-matched)

| Fix | Location | Description |
|-----|----------|-------------|
| Entry condition spike detection | Line 436 | `dataframe[1].max()` — fires on any row exceeding 0.55 in lookback window |
| Confirm entry — read probability | Line 557 | `signal_candle[1]` — reads col 1 (positive-class prob), not `&-target` label |
| BTC trend hard gate | Lines 566-567 | Deny entry if `btc_trend < 0.002` |
| 6h negative-profit time exit | Lines 527-528 | Hard exit after 360 min if unrealized P&L < 0 |
| Confirm exit — read probability | Line 607 | `signal_candle[1]` — same column fix for exit path |

### 2. FreqTrade internal (baked into `2026.4_freqai` image — NOT on host tree)

| File | Fix | Notes |
|------|-----|-------|
| `data_drawer.py` lines 368-369 | `labels_std` existence guard | Prevents KeyError if key absent |
| `XGBoostClassifier.py` lines 79-81 | Bypass label encode/rename | Removes LabelEncoder chain that caused `ValueError: y contains previously unseen labels: [1]` |
| `data_kitchen.py` line 904 | `is_string_dtype` guard | Prevents int/str mismatch in `remove_features_from_df` |

**Important:** Host patches to `/home/shad/.../freqtrade/freqai/` are never loaded by the container. The container uses its own image-installed packages at `/freqtrade/freqtrade/`. All internal fixes are baked into the `2026.4_freqai` image and verified present.

---

## What Caused the v4 Failures

### Root cause chain (9-loss run):
1. `confirm_trade_entry` line 540 read `&-target` (binary label) instead of column 1 (probability) → always `1.0` → no real filtering
2. BTC trend ≥ 0.002 gate was the ONLY real filter → entries fired on thin regime flashes (+0.0012 BTC trend) that immediately reversed
3. No time exit → losing positions held indefinitely

### Schema mismatch cascade:
1. Old model `leah_v3_vol` trained under v2025.9 — `pair_dictionary` had empty `labels_std` keys
2. Container running v2026.4 — `data_drawer.py` line 369 crashes on missing `labels_std` key
3. KeyError in `attach_return_values_to_dataframe` → predictions fall back to prob=0.0 → no entries possible
4. Fresh model `leah_v4_1` trained under v2026.4 writes its own schema → KeyError persists → pipeline fix needed

### Secondary bugs (v2026.4 upstream):
- `XGBoostClassifier.predict` runs LabelEncoder rename before `fit_live_predictions()` populates `dk.data["labels_std"]` → `ValueError: y contains previously unseen labels: [1]`
- `data_kitchen.remove_features_from_df` calls `str.startswith()` on integer column names → `AttributeError: 'int' object has no attribute 'startswith'`

---

## Image Pinning

**Current:** `freqtradeorg/freqtrade:2026.4_freqai`
**Pinned in:** `docker-compose.yml`

Do NOT use `stable_freqai` — it tracks `latest` and silently updates.

To pin a specific version:
```bash
# Find available tags
docker images | grep freqtrade

# Update compose file
sed -i 's/image: freqtradeorg\/freqtrade:.*/image: freqtradeorg\/freqtrade:2026.4_freqai/' ~/freqtrade-lea-new/docker-compose.yml

# Restart
docker compose -f ~/freqtrade-lea-new/docker-compose.yml down
docker compose -f ~/freqtrade-lea-new/docker-compose.yml up -d
```

---

## Model Training — Fresh Train Checklist

After any model delete/retrain:
1. Monitor first inference cycle for KeyErrors in logs
2. Confirm `confirm DENIED` logs show real probabilities (0.17-0.35 range, not 1.0000)
3. Confirm `prob=` values in DENIED logs are genuine float probabilities
4. If KeyError appears on a fresh train → apply `data_drawer.py` defensive patch (temporary, until upstream fixes)

---

## Validation Run

- **Bot:** freqtrade-lea-new (docker, `2026.4_freqai`)
- **Strategy:** LeahAI v4.1
- **Config:** config_lea_v4.json → identifier `leah_v4_1`
- **Database:** tradesv3_lea_v2.sqlite
- **Validation goal:** ≥$0.10 expectancy per trade over 50 trades
- **Kill criterion:** <$0.05 expectancy
- **Current:** 0 trades — pipeline clean, awaiting BTC trend push above 0.002 threshold with supporting probability

---

## Known Failure Modes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `prob=1.0000` in logs | Reading `&-target` label instead of column 1 probability | Check `confirm_trade_entry` line 540 and `custom_exit` line 590 — must read `signal_candle[1]` |
| `KeyError: 'labels_std'` | Schema mismatch — model trained under different FreqTrade version | Delete model, retrain under same version as container image |
| Entries not firing despite high max probability | Entry condition checking `iloc[-1]` instead of `.max()` | Change to `dataframe[1].max() > 0.55` in `populate_entry_trend` |
| All entries denied but BTC trend above threshold | Probability below 0.55 threshold | Model correctly filtering — wait for BTC momentum to strengthen |
| Container silently has different code than host | Host patches go to source tree container doesn't read | Always patch inside the container or use image-pinned variants |

---

## Git Workflow

```bash
# Never commit container-patch artifacts to strategy repo
git checkout freqtrade/  # revert FreqTrade internal changes

# Strategy changes only
git add user_data/strategies/LeahAI.py
git add config_lea.json  # if changed
git commit -m "leah v4.1: column fix, btc trend gate, 6h time exit"
```