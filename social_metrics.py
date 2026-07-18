#!/usr/bin/env python3
"""
Social/Market Metrics Fetcher for LeahAI v4.4
==============================================
Pulls free market data for BTC, ETH, SOL, LINK.
Social data (Twitter correlation) requires LunarCrush paid tier.

Free data sources:
- Fear & Greed Index: alternative.me
- Market data: CoinGecko
- Funding rates: Binance Futures public API
"""

import json
import urllib.request
import urllib.error
from datetime import datetime

COINS = ["bitcoin", "ethereum", "solana", "chainlink"]
COIN_SYMBOLS = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "chainlink": "LINK"}


def fetch_fear_greed():
    """Fetch Fear & Greed Index from alternative.me"""
    url = "https://api.alternative.me/fng/?limit=1"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
            v = data["data"][0]
            return {
                "value": int(v["value"]),
                "classification": v["value_classification"],
                "timestamp": int(v["timestamp"])
            }
    except Exception as e:
        return {"error": str(e)}


def fetch_market_data():
    """Fetch market data from CoinGecko"""
    ids = ",".join(COINS)
    url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}&order=market_cap_desc&sparkline=false&price_change_percentage=24h"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
            result = {}
            for c in data:
                cid = c["id"]
                result[cid] = {
                    "symbol": COIN_SYMBOLS.get(cid, cid.upper()),
                    "price": c["current_price"],
                    "change_24h_pct": c.get("price_change_percentage_24h", 0),
                    "volume_24h_usd": c["total_volume"],
                    "market_cap_usd": c["market_cap"],
                    "market_cap_rank": c.get("market_cap_rank"),
                }
            return result
    except Exception as e:
        return {"error": str(e)}


def fetch_funding_rates():
    """Fetch funding rates from Binance Futures (public, no auth)"""
    # Binance funding rates are on the USD-M futures API
    url = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT"
    rates = {}
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT"]
    for sym in symbols:
        url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={sym}"
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
                # Funding rate is in the mark price response
                # Actual funding rate: /fapi/v1/fundingRate?symbol=XXX
        except:
            pass
    
    # Use the funding rate endpoint
    for sym in symbols:
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=1"
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
                if data:
                    rates[sym] = float(data[0]["fundingRate"]) * 100  # as percentage
        except Exception:
            rates[sym] = None
    return rates


def main():
    print(f"=== LeahAI Market & Sentiment Data ===")
    print(f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print()
    
    # Fear & Greed
    fg = fetch_fear_greed()
    if "error" not in fg:
        print(f"Fear & Greed: {fg['value']} ({fg['classification']})")
    else:
        print(f"Fear & Greed: ERROR - {fg['error']}")
    print()
    
    # Market data
    market = fetch_market_data()
    if "error" not in market:
        print("Market Data:")
        for cid, d in market.items():
            sym = d["symbol"]
            print(f"  {sym}: ${d['price']:,.2f} | 24h: {d['change_24h_pct']:+.2f}% | vol: ${d['volume_24h_usd']/1e6:.0f}M | mc: ${d['market_cap_usd']/1e9:.1f}B")
    else:
        print(f"Market Data: ERROR - {market['error']}")
    print()
    
    # Funding rates
    rates = fetch_funding_rates()
    print("Funding Rates (Binance Futures):")
    mapping = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL", "LINKUSDT": "LINK"}
    for sym, label in mapping.items():
        val = rates.get(sym)
        if val is not None:
            sign = "+" if val >= 0 else ""
            print(f"  {label}: {sign}{val:.4f}%")
        else:
            print(f"  {label}: N/A")
    print()
    
    print("Note: Social data (Twitter mentions, sentiment) requires LunarCrush Individual+ ($5/day)")
    print("Fear & Greed and market data are free and refreshing every ~5min.")


if __name__ == "__main__":
    main()
