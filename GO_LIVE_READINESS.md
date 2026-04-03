# Go-Live Readiness Assessment
**Date:** March 27, 2026
**Current Status:** 🟡 NOT READY - Still in validation phase
**Target Go-Live:** April 10, 2026 (2 weeks minimum)

---

## Current Status

### ✅ What's Ready
- [x] Three bot strategies deployed and running
- [x] Paper trading (dry-run) active and collecting real data
- [x] LeaFreqAI improvements deployed today
- [x] Monitoring and diagnostic systems operational
- [x] Database tracking and performance metrics working
- [x] systemd services configured with auto-restart

### ❌ What's NOT Ready
- [ ] 2-week validation period completed
- [ ] Performance aligned with backtest expectations
- [ ] Consistent profitability demonstrated
- [ ] Real capital account configured
- [ ] Risk limits defined for live trading
- [ ] Emergency stop procedures tested
- [ ] Real exchange API keys configured

---

## Go-Live Timeline

### Phase 1: Validation (March 27 - April 3, 2026) - THIS WEEK
**Objective:** Confirm improvements work as expected

**Daily Tasks:**
```bash
# Every morning
python3 scripts/daily_scorecard.py

# Watch for:
✓ LEA entries drop to 30-40/day (from 56)
✓ LEA win rate ≥ 50% (was 51.6%)
✓ Daily P&L breakeven or slightly positive
✓ No new errors in logs
```

**Success Criteria (end of week):**
- [x] LeaFreqAI entries reduced 45%+ ← IMPLEMENT THIS WEEK
- [x] Entry quality improved (fewer marginal signals)
- [ ] No crashes or data integrity issues
- [ ] All bots maintain >95% uptime
- [ ] Logs are clean (no warnings/errors)

**Decision Point (April 3):**
- ✅ If all criteria met → Proceed to Phase 2
- ❌ If issues found → Fix and restart 1-week clock

---

### Phase 2: Extended Validation (April 3-10, 2026) - WEEK 2
**Objective:** Confirm sustained profitability

**Daily Tasks:**
```bash
# Continue monitoring
python3 scripts/daily_scorecard.py

# Run backtest with live data
scripts/research_bots.sh backtest lea 20260327-20260410
scripts/research_bots.sh backtest finagent 20260327-20260410

# Watch for:
✓ P&L trending positive (cumulative)
✓ Win rate consistent 50%+
✓ No unexpected drawdowns
```

**Success Criteria (end of week 2):**
- [ ] 7+ days of live data collected
- [ ] Cumulative P&L positive or breakeven
- [ ] Backtest results match live performance (±0.5%)
- [ ] Win rates meet or exceed targets
- [ ] Maximum drawdown acceptable (<5%)
- [ ] All three bots profitable or near-breakeven

**Decision Point (April 10):**
- ✅ If all criteria met → Ready for Go-Live
- ⚠️  If marginal results → 1 more week validation
- ❌ If negative results → Debug and fix, restart clock

---

### Phase 3: Live Trading Preparation (April 8-10, 2026)
**Objective:** Set up live trading infrastructure

**Tasks:**
1. [ ] Configure real exchange account (small capital)
2. [ ] Test API keys with live connection (no orders)
3. [ ] Set up position sizing limits
   - LeaFreqAI: 0.01 BTC per trade max
   - FinAgent: 0.005 BTC per trade max
   - Diagnostic: monitoring only (no capital)
4. [ ] Define emergency stop procedures
5. [ ] Set up alerts (Telegram/email)
6. [ ] Create runbook for live trading
7. [ ] Test rollback procedures

---

### Phase 4: Go-Live (April 10, 2026)
**Objective:** Deploy with real capital

**Pre-Launch Checklist:**
- [ ] All validation criteria met
- [ ] Live account funded with initial capital (0.1-0.5 BTC)
- [ ] API keys configured and tested
- [ ] Alerts configured and verified
- [ ] Emergency procedures documented
- [ ] Backup exit plan documented
- [ ] Team notifications sent

**Launch Day:**
1. Switch `"dry_run": true` → `"dry_run": false` in config
2. Restart all bot services
3. Verify live orders executing (small initial trades)
4. Monitor closely for first 4 hours
5. Document any issues

**First Week Live:**
- Monitor every 6 hours
- Check for slippage/execution issues
- Verify fills are within acceptable range
- Be ready to pause if issues arise

---

## Success Metrics for Go-Live Approval

### Minimum Requirements (ALL MUST BE MET)
```
✓ LeaFreqAI:
  • Win rate ≥ 50%
  • Profit factor ≥ 0.80
  • Daily P&L: breakeven or positive (7-day average)
  • No drawdown > 5%

✓ FinAgent:
  • Win rate ≥ 25%
  • Consistent losses < 1% per day
  • Max drawdown < 2%
  • Reliable position management

✓ System Health:
  • >95% uptime
  • Clean logs (no errors)
  • Database integrity verified
  • All alerts working
```

### Ideal Requirements (NICE TO HAVE)
```
+ Combined portfolio:
  • Positive cumulative return
  • Correlation < 0.5 between strategies
  • Risk-adjusted Sharpe ratio > 1.0

+ Market conditions:
  • Tested in trending market
  • Tested in sideways market
  • Tested in volatile market
```

---

## Risk Assessment

### Current Risks (Dry-Run Phase)
| Risk | Level | Mitigation |
|------|-------|-----------|
| Strategy hasn't proven live | 🔴 High | Running validation now |
| Model overfitting | 🟡 Medium | Cross-validation in testing |
| Execution/slippage unknown | 🟡 Medium | Will test in Phase 4 |
| Infrastructure issues | 🟢 Low | systemd auto-restart, monitoring |

### Go-Live Risks (Can be managed)
| Risk | Level | Mitigation |
|------|-------|-----------|
| Real capital at risk | 🟡 Medium | Start small (0.1-0.5 BTC) |
| Unknown market conditions | 🟡 Medium | Diversified pair selection |
| Execution failures | 🟢 Low | Small position sizes, alerts |
| Model degradation | 🟡 Medium | Daily retraining, monitoring |

---

## Capital Requirements

### Recommended Starting Capital
```
Total Portfolio: 0.3 BTC (~$12k at current prices)

Allocation:
├─ LeaFreqAI:   0.15 BTC (50%) - Growth focused
├─ FinAgent:    0.10 BTC (33%) - Defensive
├─ Diagnostic:  0.05 BTC (17%) - Reference/testing
└─ Reserve:     0.05 BTC      - Emergencies

Per-Trade Limits:
├─ LeaFreqAI:   0.01 BTC max stake
├─ FinAgent:    0.005 BTC max stake
└─ Total open:  0.03 BTC max across all
```

### Why This Size?
- **Small enough** to limit losses if models fail
- **Large enough** to generate meaningful signals (avoid commission drag)
- **Diversified** across strategies reduces single-strategy risk
- **Testable** in 2 weeks without massive P&L swings

---

## Decision Tree

```
TODAY (March 27)
   ↓
Deploy LEA improvements ✅
   ↓
March 27-April 3: VALIDATION WEEK 1
   ├─ Daily scorecard review
   ├─ Check entry count (5.6 → 3.0 reduction)
   └─ Monitor P&L trend
      ↓
   April 3 Decision:
   ├─ ✅ All metrics met? → Continue to Week 2
   ├─ ⚠️  Mixed results? → Debug & restart clock
   └─ ❌ Failed? → Rollback, troubleshoot
      ↓
April 3-10: VALIDATION WEEK 2
   ├─ Backtest current period
   ├─ Check sustained profitability
   ├─ Verify backtest vs live match
   └─ Finalize live account setup
      ↓
   April 10 Decision:
   ├─ ✅ All metrics met? → GO LIVE (Phase 4)
   ├─ ⚠️  Marginal results? → 1 more week
   └─ ❌ Failed? → Extended troubleshooting
      ↓
April 10+: LIVE TRADING
   ├─ Start with 0.1 BTC initial capital
   ├─ Monitor closely for 1 week
   ├─ Scale up gradually if successful
   └─ Maintain daily monitoring
```

---

## Weekly Checkpoints

### Week 1 (March 27 - April 3)
```
Monday (Mar 27):    Implement LEA improvements, restart bot
Tuesday-Thursday:   Monitor daily, verify entry reduction
Friday (Apr 3):     Decision meeting, review metrics
```

### Week 2 (April 3-10)
```
Monday (Apr 3):     Confirm Week 1 success, begin backtest
Tuesday-Thursday:   Continue monitoring, verify consistency
Friday (Apr 10):    Final decision on go-live
```

---

## Go-Live Preparation Checklist

### Before April 10
- [ ] Validate LeaFreqAI improvements working
- [ ] Run full backtest on updated strategy
- [ ] Document performance metrics
- [ ] Identify and fix any remaining issues
- [ ] Create live trading runbook
- [ ] Test emergency stop procedures
- [ ] Brief team on go-live plan

### April 8-10 (Final Preparation)
- [ ] Set up live exchange account
- [ ] Configure API keys (test mode first)
- [ ] Test live data feeds
- [ ] Verify position sizing logic
- [ ] Set up alerts/notifications
- [ ] Document rollback procedures
- [ ] Final code review

### April 10 (Launch Day)
- [ ] Toggle dry_run to false
- [ ] Restart bot services
- [ ] Monitor closely for first 4 hours
- [ ] Verify first live orders execute
- [ ] Check fill prices vs market
- [ ] Document any issues

---

## Emergency Procedures

### If Issues Arise
```
CRITICAL (Stop immediately):
- Model returns NaN or infinite values
- Database corruption detected
- Order execution failures
- Exchange API down/unreliable
→ ACTION: Restart bots in dry-run, investigate

SERIOUS (Pause trading):
- Drawdown > 3% in single day
- Win rate drops < 30% (rolling 24h)
- More than 2 consecutive losing trades
- Unusual order fills (slippage > 1%)
→ ACTION: Pause trading, analyze, resume if resolved

MINOR (Monitor closely):
- Single losing trade
- High volatility
- Slippage 0.5-1%
→ ACTION: Continue trading, document pattern
```

---

## Success = Live Trading

**Green Light (April 10, 2026):**
- ✅ 2+ weeks of validated dry-run performance
- ✅ Backtest results match live performance
- ✅ All three bots operational and reliable
- ✅ Performance within expected ranges
- ✅ Risk management working correctly
- ✅ Team confident in go-live

**Result:** Launch with 0.1 BTC initial capital
- Start small, prove consistency
- Scale gradually if successful (0.2, 0.5 BTC)
- Monitor daily for first month

---

## Timeline Summary

```
TODAY:        March 27  - Deploy LEA improvements
WEEK 1:       March 27  - April 3   - Validation Phase 1
WEEK 2:       April 3   - April 10  - Validation Phase 2
GO-LIVE:      April 10  - Live trading begins
SCALE-UP:     April 20+ - Increase capital if performing
```

**Minimum Time to Go-Live:** 2 weeks (April 10)
**Realistic Time:** 3-4 weeks (April 17-24) if issues found
**Conservative Approach:** 1 month (May 1) with extended validation

---

## Current Blockers

🔴 **Critical Path Item:**
- LeaFreqAI improvements must be validated (in progress)
- Once validated, all other items can proceed in parallel

---

**Status:** ⏳ Waiting for validation data (end of week 1)
**Next Review:** April 3, 2026 (1 week)
**Decision Maker:** Review success metrics + team assessment

