#!/usr/bin/env python3
import sqlite3, glob

conn = sqlite3.connect('/freqtrade/user_data/tradesv3_lea.sqlite')
trades = conn.execute(
    "SELECT pair, open_date, realized_profit, exit_reason FROM trades "
    "WHERE is_open=0 ORDER BY open_date DESC LIMIT 100"
).fetchall()
conn.close()

# Build regime map
cache = {}
for pair_file in set(t.replace('/', '_').replace('_USDT', '') + '_USDT' for t, _, _, _ in trades):
    pattern = f'/freqtrade/user_data/data/binance/{pair_file}-15m.feather'
    files = glob.glob(pattern)
    if files:
        try:
            df = __import__('pandas').read_feather(files[0])
            df['sma20'] = df['close'].rolling(20).mean()
            df['sma50'] = df['close'].rolling(50).mean()
            df['reg'] = (df['sma20'] > df['sma50']).astype(int)
            cache[pair_file] = df
        except:
            pass

def get_regime(pair, date):
    pf = pair.replace('/', '_')
    if pf not in cache:
        return -1
    try:
        dt = __import__('pandas').to_datetime(date).tz_localize('UTC')
        v = cache[pf][cache[pf]['date'] <= dt]
        return int(v.iloc[-1]['reg']) if len(v) > 0 else -1
    except:
        return -1

regimes = [get_regime(t[0], t[1]) for t in trades]

up_trades = [(t[0],t[2],t[3]) for t,r in zip(trades,regimes) if r == 1]
down_trades = [(t[0],t[2],t[3]) for t,r in zip(trades,regimes) if r == 0]

def stats(label, ts):
    if not ts:
        print(f"{label}: no trades")
        return
    profits = [t[1] for t in ts]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    wr = len(wins) / len(profits) * 100 if profits else 0
    avg_w = sum(wins)/len(wins) if wins else 0
    avg_l = sum(losses)/len(losses) if losses else 0
    total = sum(profits)
    exp = (wr/100 * avg_w) + ((100-wr)/100 * avg_l)
    print(f"\n{label}")
    print(f"  Count: {len(ts)}")
    print(f"  Win rate: {wr:.1f}%")
    print(f"  Avg winner: +{avg_w:.4f}")
    print(f"  Avg loser: {avg_l:.4f}")
    print(f"  L/W ratio: {abs(avg_l)/avg_w:.2f}x" if avg_w else " N/A")
    print(f"  Expectancy: {exp:+.4f}")
    print(f"  Total PnL: {total:+.4f}")

stats("UPTREND:", up_trades)
stats("DOWNTREND:", down_trades)