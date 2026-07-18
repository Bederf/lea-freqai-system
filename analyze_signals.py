import re

lines = open('/home/shad/lea-freqai-system/validation_v4_3_probwatch.log').readlines()

denial_prob = 0
denial_btc = 0
denial_ema = 0
approved = 0
high_prob_signals = []

for line in lines:
    m = re.search(r'last=([0-9.]+)', line)
    if not m: continue
    last = float(m.group(1))
    btc = float(re.search(r'btc_trend=([+-]?[0-9.]+)', line).group(1))
    ema = re.search(r'above_ema50=(True|False)', line).group(1) == 'False'
    
    if last < 0.55:
        denial_prob += 1
    if btc < 0.002:
        denial_btc += 1
    if ema:
        denial_ema += 1
    if last >= 0.55:
        approved += 1
    if last > 0.60:
        pair = re.search(r'\[([^\]]+)\]', line).group(1)
        high_prob_signals.append((pair, last, btc))

print(f"DENIED: prob < 0.55: {denial_prob}")
print(f"DENIED: btc_trend < 0.002: {denial_btc}")
print(f"DENIED: above_ema50=False: {denial_ema}")
print(f"APPROVED (new): {approved}")
print(f"Total lines: {len(lines)}")
print(f"\nHigh-Prob Signals (> 0.60):")
for pair, prob, btc in high_prob_signals:
    print(f"  {pair} prob={prob} @ btc_trend={btc:+.4f}")
