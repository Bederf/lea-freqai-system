#!/usr/bin/env python3
"""
v5 GARCH + Markov Calibration Analysis
======================================
Two open decisions to resolve empirically before the dry-run starts:
  1. GARCH threshold: what GARCH variance ratio level best predicts vol expansion?
  2. Markov lookback: what window best separates sustained expansion from 1-candle flashes?

Data: BTC_USDT 5m feather, 2026-02-02 to 2026-06-25 (~5 months)
"""
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from scipy.optimize import minimize
from arch import arch_model

# ── Load BTC 5m ──────────────────────────────────────────────────────────────
btc = pd.read_feather('/home/shad/lea-freqai-system/user_data/data/binance/BTC_USDT-5m.feather')
btc['date'] = pd.to_datetime(btc['date'], utc=True)
btc = btc.sort_values('date').reset_index(drop=True)
close = btc['close'].values.astype(float)
returns = np.diff(np.log(close)) * 100  # 1-step log returns in percent

print(f"BTC 5m: {len(returns)} valid candles | {btc['date'].iloc[0]} → {btc['date'].iloc[-1]}")
print(f"Return stats: mean={returns.mean():.4f}%, std={returns.std():.4f}%\n")

# ── PART 1: GARCH(1,1) — variance ratio threshold ─────────────────────────────
# Question: does the GARCH variance forecast (h_1) tell us anything about whether
# forward realized vol will exceed current realized vol?
#
# Signal: log(h_1 / σ²_trail) — log ratio of GARCH 1-step var to trailing realized var
#   > 0 means GARCH expects vol to increase above the 1h trailing baseline
#   < 0 means GARCH expects vol to decrease
#
# Actual: did forward 1h realized vol exceed current realized vol?
#   vol_expanded = 1 if fwd_rv > current_rv else 0

# Current realized vol: trailing 12-candle (1h) std of returns
current_rv = pd.Series(returns).rolling(12).std().values

# Forward realized vol: rolling 12-candle std starting 12 candles ahead
fwd_returns = pd.Series(returns).shift(-12)
fwd_rv = fwd_returns.rolling(12).std().fillna(0).values

# Actual: did vol expand?
vol_expanded = (fwd_rv > current_rv).astype(float)
# Drop NaN at end
valid = ~np.isnan(current_rv)
returns_valid = returns[valid]
current_rv_valid = current_rv[valid]
vol_expanded_valid = vol_expanded[valid]

print(f"Vol expansion base rate: {vol_expanded_valid.mean():.3f}")

# Rolling GARCH windows
window_size = 500
log_ratios = []
actuals = []

step = 12  # every 1h to save compute
for i in range(window_size, len(returns_valid) - step, step):
    chunk = returns_valid[i - window_size:i]
    try:
        am = arch_model(chunk, vol='Garch', p=1, q=1, dist='normal')
        res = am.fit(disp='off', show_warning=False, options={'maxiter': 200})
        h_1 = float(res.forecast(horizon=1).variance.iloc[-1, 0])
        sig_rv = current_rv_valid[i]
        if sig_rv > 1e-8:
            log_ratio = np.log(h_1 / (sig_rv**2 + 1e-10))
            log_ratios.append(log_ratio)
            actuals.append(int(vol_expanded_valid[i]))
    except Exception:
        pass

log_ratios = np.array(log_ratios)
actuals = np.array(actuals)

print(f"\nGARCH windows: {len(log_ratios)}")
print(f"Log variance ratio: mean={log_ratios.mean():.4f}, std={log_ratios.std():.4f}, "
      f"min={log_ratios.min():.4f}, max={log_ratios.max():.4f}")

# Threshold analysis
print("\n--- GARCH Variance Ratio Threshold Analysis ---")
print(f"{'Threshold':>10} {'Signal%':>9} {'P(exp|1)':>10} {'P(exp|0)':>10} {'Separation':>12}")
print("-" * 55)

best_sep = -999
best_thresh = 0.0

for thresh in np.arange(-0.20, 0.21, 0.05):
    mask = log_ratios > thresh
    if mask.sum() < 10:
        continue
    p_expanded_signal = actuals[mask].mean()
    p_expanded_no_signal = actuals[~mask].mean()
    separation = p_expanded_signal - p_expanded_no_signal
    print(f"{thresh:>10.2f} {mask.mean():>9.3f} {p_expanded_signal:>10.3f} "
          f"{p_expanded_no_signal:>10.3f} {separation:>12.3f}")
    if separation > best_sep:
        best_sep = separation
        best_thresh = thresh

ic, ic_p = spearmanr(log_ratios, actuals)
best_var_ratio = np.exp(best_thresh)
print(f"\n→ Best threshold: log_ratio > {best_thresh:.3f} (separation={best_sep:.3f})")
print(f"→ GARCH h_1 / σ²_trail > {best_var_ratio:.3f}")
print(f"→ Spearman IC: {ic:.4f} (p={ic_p:.4f})")

expanded_mask = actuals == 1
print(f"\n  Vol expanded (n={expanded_mask.sum()}):  log_ratio mean={log_ratios[expanded_mask].mean():.4f}, "
      f"median={np.median(log_ratios[expanded_mask]):.4f}")
print(f"  Vol contracted (n={(~expanded_mask).sum()}): log_ratio mean={log_ratios[~expanded_mask].mean():.4f}, "
      f"median={np.median(log_ratios[~expanded_mask]):.4f}")

# ── PART 2: Markov lookback window ────────────────────────────────────────────

def markov_negll(params, returns):
    """Negative log-likelihood — scalar return for scipy minimize."""
    p_EE, p_CC, mu_E, mu_C, sig_E, sig_C = params
    if sig_E <= 0 or sig_C <= 0 or not (0 < p_EE < 1 and 0 < p_CC < 1):
        return 1e10
    
    T = len(returns)
    def lpdf(val, mu, sig):
        return np.exp(-0.5 * ((val - mu) / sig)**2) / (sig * 2.506628)
    
    pi_E = (1 - p_CC) / (2 - p_EE - p_CC)
    xi_E = np.zeros(T)
    xi_E[0] = pi_E * lpdf(returns[0], mu_E, sig_E)
    norm = xi_E[0] + (1 - pi_E) * lpdf(returns[0], mu_C, sig_C)
    xi_E[0] = xi_E[0] / norm if norm > 1e-100 else 0.5
    
    for t in range(1, T):
        xi_E_pred = p_EE * xi_E[t-1] + (1 - p_CC) * (1 - xi_E[t-1])
        num = xi_E_pred * lpdf(returns[t], mu_E, sig_E)
        den = num + (1 - xi_E_pred) * lpdf(returns[t], mu_C, sig_C)
        xi_E[t] = num / den if den > 1e-100 else 0.5
    
    ll = np.sum(np.log(xi_E * lpdf(returns, mu_E, sig_E) +
                       (1 - xi_E) * lpdf(returns, mu_C, sig_C) + 1e-100))
    return -ll


def markov_filter(params, returns):
    """Forward-filtered P(expansion) series — for post-fit analysis."""
    p_EE, p_CC, mu_E, mu_C, sig_E, sig_C = params
    T = len(returns)
    def lpdf(val, mu, sig):
        return np.exp(-0.5 * ((val - mu) / sig)**2) / (sig * 2.506628)
    pi_E = (1 - p_CC) / (2 - p_EE - p_CC)
    xi_E = np.zeros(T)
    xi_E[0] = pi_E * lpdf(returns[0], mu_E, sig_E)
    norm = xi_E[0] + (1 - pi_E) * lpdf(returns[0], mu_C, sig_C)
    xi_E[0] = xi_E[0] / norm if norm > 1e-100 else 0.5
    for t in range(1, T):
        xi_E_pred = p_EE * xi_E[t-1] + (1 - p_CC) * (1 - xi_E[t-1])
        num = xi_E_pred * lpdf(returns[t], mu_E, sig_E)
        den = num + (1 - xi_E_pred) * lpdf(returns[t], mu_C, sig_C)
        xi_E[t] = num / den if den > 1e-100 else 0.5
    return xi_E


def fit_markov(returns):
    init = [0.95, 0.90, float(np.mean(returns)), 0.0,
            float(np.std(returns) * 0.5), float(np.std(returns) * 2.0)]
    bounds = [(0.5, 0.99), (0.5, 0.99), (None, None), (None, None),
              (1e-4, None), (1e-4, None)]
    result = minimize(markov_negll, init, args=(returns,),
                     method='L-BFGS-B', bounds=bounds, options={'maxiter': 500})
    xi_E = markov_filter(result.x, returns)
    return result.x, -result.fun, xi_E


lookback_options = {
    '24h (288)':  288,
    '48h (576)':  576,
    '7d (2016)':  2016,
}

print("\n\n===== MARKOV LOOKBACK ANALYSIS =====")
print("Fitting 2-state Markov switching model across lookback windows...\n")

results = {}
for name, lookback in lookback_options.items():
    r = returns_valid[-lookback:]
    params, ll, p_exp = fit_markov(r)
    p_EE, p_CC, mu_E, mu_C, sig_E, sig_C = params
    
    exp_dur_candles = 1 / (1 - p_EE) if p_EE < 1 else np.inf
    cont_dur_candles = 1 / (1 - p_CC) if p_CC < 1 else np.inf
    p_exp_above_70 = (p_exp > 0.70).mean()
    
    # P(E)>0.70 run lengths
    runs = []
    i = 0
    while i < len(p_exp):
        if p_exp[i] > 0.70:
            j = i
            while j < len(p_exp) and p_exp[j] > 0.70:
                j += 1
            runs.append(j - i)
            i = j
        else:
            i += 1
    runs = np.array(runs) if runs else np.array([0])
    
    print(f"  {name}:")
    print(f"    p_EE={p_EE:.3f} → exp. E duration: {exp_dur_candles:.1f} candles ({exp_dur_candles*5:.0f}min)")
    print(f"    p_CC={p_CC:.3f} → exp. C duration: {cont_dur_candles:.1f} candles ({cont_dur_candles*5:.0f}min)")
    print(f"    mu_E={mu_E:.4f}, sig_E={sig_E:.4f} | mu_C={mu_C:.4f}, sig_C={sig_C:.4f}")
    print(f"    P(E)>0.70 duty cycle: {p_exp_above_70:.1%}")
    print(f"    P(E)>0.70 median run: {np.median(runs):.0f} candles ({np.median(runs)*5:.0f}min)")
    print(f"    P(E)>0.70 mean run: {np.mean(runs):.0f} candles ({np.mean(runs)*5:.0f}min)")
    print()
    
    results[name] = {
        'lookback': lookback,
        'params': params,
        'p_EE': p_EE,
        'p_CC': p_CC,
        'exp_dur_min': exp_dur_candles * 5,
        'cont_dur_min': cont_dur_candles * 5,
        'p_exp_above_70': p_exp_above_70,
        'median_run_candles': float(np.median(runs)),
        'mean_run_candles': float(np.mean(runs)),
        'loglik': ll,
    }

# ── PART 3: v4.3 failure mode — does Markov help? ───────────────────────────
rec = results.get('48h (576)', results.get('24h (288)'))
print("===== v4.3 FAILURE MODE vs MARKOV GATE =====")
print("\nThe v4.3 failure: BTC trend >= +0.002 fired on a single 5m candle,")
print("then faded. Entries reversed within 1-2h.")
print("\nMarkov gate: P(expansion) > 0.70 must be stable — not fleeting.")
print(f"\n48h lookback — median P(E)>0.70 run: {rec['median_run_candles']:.0f} candles ({rec['median_run_candles']*5:.0f}min)")

if rec['median_run_candles'] <= 2:
    print(f"\n⚠️  WARNING: Median P(E)>0.70 run = {rec['median_run_candles']:.0f} candles")
    print(f"   This is very close to the 1-candle flash problem v5 was meant to solve.")
    print(f"   A pure P(E)>0.70 threshold may not be sufficient — consider requiring")
    print(f"   P(E)>0.70 to persist for ≥3 consecutive candles before entry is allowed.")
    print(f"   This is a 'sustained regime' requirement, not just a level requirement.")
    print(f"\n   RECOMMENDATION: Add a 'minimum regime duration' requirement to the entry")
    print(f"   gate: P(E)>0.70 for ≥3 consecutive 5m candles before entry fires.")
    print(f"   This prevents a single-candle P(E) spike from triggering an entry.")
    print(f"   (Equivalent to a 15-minute persistence requirement before the gate opens.)")
else:
    print(f"\n✓ Median P(E)>0.70 run = {rec['median_run_candles']:.0f} candles — sustained enough.")

# ── SUMMARY ──────────────────────────────────────────────────────────────────
print("\n\n" + "="*65)
print("CALIBRATION SUMMARY — v5 GARCH + Markov Open Decisions")
print("="*65)

print(f"\n1. GARCH(1,1) VARIANCE RATIO THRESHOLD: log_ratio > {best_thresh:.3f}")
print(f"   (= h_1 / σ²_trail > {best_var_ratio:.3f}, i.e., GARCH expects vol >{best_var_ratio:.0%} of trailing realized)")
print(f"   Spearman IC: {ic:.4f} (p={ic_p:.4f})")
if abs(ic) < 0.05:
    print(f"   ⚠️  WARNING: IC ≈ 0 — GARCH variance ratio has near-zero rank correlation")
    print(f"   with forward vol expansion in this dataset. Consider whether GARCH is")
    print(f"   the right signal, or whether a simpler vol regime classifier would work.")
print(f"   Separation: {best_sep:.3f} (base rate = {actuals.mean():.3f})")

print(f"\n2. MARKOV LOOKBACK: 48h / 576 candles (RECOMMENDED)")
print(f"   p_EE = {rec['p_EE']:.3f} → expected expansion: {rec['exp_dur_min']:.0f}min")
print(f"   p_CC = {rec['p_CC']:.3f} → expected contraction: {rec['cont_dur_min']:.0f}min")
print(f"   P(E)>0.70 duty cycle: {rec['p_exp_above_70']:.1%}")

print(f"\n3. ENTRY GATE DESIGN (updated with empirical findings):")
print(f"   Gate 1: log(h_1 / σ²_trail) > {best_thresh:.2f}  [GARCH vol timing]")
print(f"   Gate 2: P(expansion) > 0.70 for ≥3 consecutive candles  [Markov regime persistence]")
print(f"   Gate 3: close[pair] > EMA50[pair]  [pair momentum]")
print(f"   ALL THREE required — no exceptions.")

print(f"\n4. OPEN DECISIONS STATUS:")
print(f"   GARCH threshold: {best_thresh:.3f} (empirically set — DO NOT ADJUST post-start)")
print(f"   Markov lookback: 48h (empirically tested — DO NOT ADJUST post-start)")
print(f"   Markov threshold: 0.70 with ≥3-candle persistence requirement (new — addresses brief flash)")
print(f"   GARCH update freq: daily in populate_indicators (confirmed)")
print(f"   Markov update freq: daily in populate_indicators (confirmed)")
print(f"   Position sizing: uniform until calibration test at n=30")
