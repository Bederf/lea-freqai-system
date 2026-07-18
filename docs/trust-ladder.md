# LeahAI Trust Ladder

**Purpose:** Single, objective view of where Leah stands at any moment. Prevents premature deployment and provides clear gating criteria. Inspired by Sentinel's safety model.

---

## Levels

| Level | Name | Requirement | Status |
|-------|------|-------------|--------|
| L0 | Strategy compiles | Code loads without SyntaxError or ImportError in container | ✅ |
| L1 | Paper trading stable | Bot runs >1h without crash, 0 open trades >20h, dry_run=true | ✅ |
| L2 | Distribution stable | v4.4 prediction means within ±0.05 of training band for 3+ consecutive cron runs | 🟡 Partial |
| **L2.5** | **Operational integrity** | **0 recurring strategy exceptions, heartbeat stable, all pair models load, no NaN/None propagation** | **✅ Achieved** |
| L3 | Positive paper expectancy | E[net_pnl] > 0 over paper trades | ⏳ Pending |
| L4 | 50+ paper trades | Minimum sample for statistical significance | ⏳ Pending |
| L5 | PF > 1.2 in paper | Profit factor as secondary confirmation | ⏳ Pending |
| L6 | Live deployment | All above + explicit human sign-off | ❌ Not reached |

---

## Current State (2026-07-15)

---

### L0 — Strategy compiles ✅
- Container starts cleanly
- LeahAI.py loads without errors
- All model files (BTC, ETH, SOL, LINK) present and loadable

### L1 — Paper trading stable ✅
- Container running 2+ hours since last restart (07:24 UTC)
- 0 open trades
- dry_run=true confirmed
- **NoneType error spam eliminated** — was 9,720+/min, now 0 post-restart (fix confirmed 2026-07-15T07:27+ UTC)

### L2.5 — Operational integrity ✅
| Check | Result |
|-------|--------|
| Runtime exceptions | 0 since restart |
| Heartbeat | Container ping OK |
| All pair models loaded | BTC, ETH, SOL, LINK verified |
| NaN/None propagation | None detected |

### L2 — Distribution stable 🟡
v4.4 shadow mode prediction distributions:

| Pair | Live Mean | Training Band | %>55 Live | Training %>55 | Status |
|------|-----------|---------------|-----------|---------------|--------|
| BTC | 0.390 | 0.32 | 8.01% | 3% | 🟡 Elevated |
| ETH | 0.358 | 0.32 | 3.05% | 3% | ✅ OK |
| SOL | 0.392 | 0.32 | 3.68% | 1% | 🟡 Elevated |
| LINK | 0.402 | 0.31 | 6.32% | 2% | 🟡 Elevated |

BTC showing largest drift from training band. ETH is stable. SOL and LINK elevated but trending toward band (were worse yesterday).

**Gate:** All pairs within ±0.05 of training mean for 3 consecutive runs.

### L3 — Positive paper expectancy ⏳
- Not yet evaluated — no trades placed
- v4.4 is shadow mode only (no capital deployed)
- E004 shows all labels have negative expectancy under current execution strategy
- Next step: paper trading mode when L2 is stable

### L4 — 50+ paper trades ⏳
- 0 trades placed (shadow mode logs but does not execute)
- Gate requires actual paper trades, not just logged predictions

### L5 — PF > 1.2 in paper ⏳
- Not evaluated (no trades)

### L6 — Live deployment ❌
- Not reached

---

## Promotions

A level is promoted when:
- The requirement is met objectively (DB query or log evidence)
- The gate is held for 3+ consecutive cron runs (no reversals)
- Pieter explicitly acknowledges the promotion

A level is demoted when:
- Objective evidence shows the gate has been violated
- A new failure mode is discovered

---

## Engineering Debt (Pre-L6)

These are not part of the Trust Ladder but must be resolved before live trading:

| Issue | Severity | Status | Notes |
|-------|----------|--------|-------|
| NoneType spam in logs | P0 | ✅ Fixed (2026-07-15) | Was 9,720+/min, now 0. Root cause: dead code block removed. |
| Timezone bug in eval harness | Low | ✅ Fixed | E004 run.py patched |
| Dead code in LeahAI.py | Medium | ✅ Fixed | Orphaned except block removed |
| Log noise (WARNING spam) | Medium | ⏳ Pending | Entry check logs every candle — make INFO or DEBUG |

---

## Strategy Freeze (Effective 2026-07-15)

**No changes to strategy logic until L3 is achieved.**

Prohibited:
- New labels or threshold changes
- New ATR filters or feature additions
- Retraining models (unless L2/L2.5 fails)

Permitted:
- Bug fixes (like the NoneType fix)
- Monitoring and evidence collection
- Trust Ladder reviews
- Infrastructure improvements

**Rationale:** The project has crossed from hypothesis exploration into validation mode. Frequent strategy changes prevent accumulating comparable data. The current frozen strategy (Label A, threshold 0.55, ATR80 filter) stays until paper trading evidence either promotes it or requires a specific, evidence-driven change.

---

## E004 Label Research — Archived (v5 Material)

Separate from Trust Ladder — research only, not deployment guidance.

**Key finding:** All candidate labels (A/B/C/D) have negative expectancy under current execution. The label is **not the primary bottleneck** — the execution strategy is. This narrows future work: do not explore new labels without also addressing execution.

**Archived as:** Research complete — candidate for Leah v5, not a production change. Do not modify production strategy based on these results.
