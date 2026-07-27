#!/bin/bash
cat >> /home/shad/lea-freqai-system/validation_v5_probwatch.log << 'EOF'
2026-07-02T06:25:03Z | LINK/USDT   | GARCH=-0.1775 | P(E)=0.8713 | persist=1 | g1=False(garch=-0.1775) g2=False(persist=1) g3=True g4=True g5=False(btc_trend=-0.0019) | NO ENTRY
2026-07-02T06:25:04Z | ETH/USDT    | GARCH=-0.1775 | P(E)=0.7009 | persist=1 | g1=False(garch=-0.1775) g2=False(persist=1) g3=False g4=True g5=False(btc_trend=-0.0019) | NO ENTRY
2026-07-02T06:25:05Z | SOL/USDT    | GARCH=-0.1775 | P(E)=0.7506 | persist=1 | g1=False(garch=-0.1775) g2=False(persist=1) g3=True g4=True g5=False(btc_trend=-0.0019) | NO ENTRY
2026-07-02T06:25:07Z | BTC/USDT    | GARCH=-0.1775 | P(E)=0.8310 | persist=3 | g1=False(garch=-0.1775) g2=True(persist=3) g3=False g4=True g5=False(btc_trend=+0.0000) | NO ENTRY
2026-07-02T06:30:02Z | LINK/USDT   | GARCH=-0.1775 | P(E)=0.0277 | persist=0 | g1=False(garch=-0.1775) g2=False(persist=0) g3=False g4=True g5=False(btc_trend=-0.0015) | NO ENTRY
2026-07-02T06:30:03Z | ETH/USDT    | GARCH=-0.1775 | P(E)=0.7555 | persist=1 | g1=False(garch=-0.1775) g2=False(persist=1) g3=False g4=True g5=False(btc_trend=-0.0015) | NO ENTRY
2026-07-02T06:30:05Z | SOL/USDT    | GARCH=-0.1775 | P(E)=0.0918 | persist=0 | g1=False(garch=-0.1775) g2=False(persist=0) g3=True g4=True g5=False(btc_trend=-0.0015) | NO ENTRY
2026-07-02T06:30:06Z | BTC/USDT    | GARCH=-0.1775 | P(E)=0.8634 | persist=4 | g1=False(garch=-0.1775) g2=True(persist=4) g3=False g4=True g5=False(btc_trend=+0.0000) | NO ENTRY
2026-07-02T06:35:02Z | LINK/USDT   | GARCH=-0.1775 | P(E)=0.0000 | persist=0 | g1=False(garch=-0.1775) g2=False(persist=0) g3=True g4=True g5=False(btc_trend=+0.0010) | NO ENTRY
2026-07-02T06:35:04Z | ETH/USDT    | GARCH=-0.1775 | P(E)=0.0000 | persist=0 | g1=False(garch=-0.1775) g2=False(persist=0) g3=True g4=True g5=False(btc_trend=+0.0010) | NO ENTRY
2026-07-02T06:35:05Z | SOL/USDT    | GARCH=-0.1775 | P(E)=0.0000 | persist=0 | g1=False(garch=-0.1775) g2=False(persist=0) g3=True g4=True g5=False(btc_trend=+0.0010) | NO ENTRY
2026-07-02T06:35:07Z | BTC/USDT    | GARCH=-0.1775 | P(E)=0.0000 | persist=0 | g1=False(garch=-0.1775) g2=False(persist=0) g3=True g4=True g5=False(btc_trend=+0.0000) | NO ENTRY
SUMMARY 06:24-06:37: 12 checks across 4 pairs. NO ENTRIES 12/12. g1(GARCH) failed 12/12 (100%). g2(persist) passed 4/12 (BTC-only). g5(BTC-trend) failed 2/12. Gate discipline SOLID - no false entries.
EOF
echo "2026-07-02T06:37:12Z" > /home/shad/lea-freqai-system/.probwatch_v5_marker
