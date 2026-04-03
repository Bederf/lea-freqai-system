## Diary Entry (tomorrow)

1. Continue running `freqtrade-diagnostic.service` to collect gate logs (`gate_summary`, `buy_blocked`, `stake_adjusted`) and verify the signal-quality risk gate is tuning itself correctly per pair.  
2. Use the diagnostic log output to adjust the weights/thresholds inside `calculate_signal_confidence()` until the gate blocks noisy predictions and reduces stakes on mixed signals without vetoing every entry.  
3. Once the gate behaves predictably, plan the next step: layering in the volatility/VaR multiplier and propagating the same gate+logging into the LEA and FinAgent strategies.

