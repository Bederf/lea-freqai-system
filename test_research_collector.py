#!/usr/bin/env python3
"""
Test script for Binance Research Collector
Verifies all data sources are working correctly
"""

import json
import sys
import time
from binance_research_collector import BinanceResearchCollector

def test_collector():
    """Test all collector functions"""
    print("=" * 80)
    print("BINANCE RESEARCH COLLECTOR - TESTING")
    print("=" * 80)
    print()
    
    # Initialize collector
    print("🔧 Initializing collector...")
    collector = BinanceResearchCollector()
    print("✅ Collector initialized")
    print()
    
    # Test 1: Fear & Greed Index
    print("📊 TEST 1: Fear & Greed Index")
    print("-" * 80)
    try:
        result = collector.get_fear_greed_index()
        print(f"✅ Fear & Greed Value: {result['fear_greed_value']}")
        print(f"   Classification: {result['fear_greed_classification']}")
        print(f"   Timestamp: {result['timestamp']}")
    except Exception as e:
        print(f"❌ Error: {e}")
    print()
    
    # Test 2: Sentiment Data
    print("📊 TEST 2: Sentiment (CoinGecko)")
    print("-" * 80)
    try:
        result = collector.get_coingecko_sentiment('bitcoin')
        print(f"✅ Bitcoin Sentiment:")
        print(f"   Votes Up: {result['sentiment_votes_up']:.1f}%")
        print(f"   Votes Down: {result['sentiment_votes_down']:.1f}%")
        print(f"   Market Cap Change 24h: {result['market_cap_change_24h']:.2f}%")
        print(f"   Volume Change 24h: {result['volume_change_24h']:.2f}%")
    except Exception as e:
        print(f"❌ Error: {e}")
    print()
    
    # Test 3: Exchange Flows
    print("📊 TEST 3: Exchange Flows (Binance)")
    print("-" * 80)
    try:
        result = collector.get_exchange_flows('BTC')
        print(f"✅ BTC Exchange Flows:")
        print(f"   Inflow: {result['exchange_inflow']:.2f}")
        print(f"   Outflow: {result['exchange_outflow']:.2f}")
        print(f"   Net Flow: {result['net_flow']:.2f}")
    except Exception as e:
        print(f"❌ Error: {e}")
    print()
    
    # Test 4: Whale Movements
    print("📊 TEST 4: Whale Movements (>$1M)")
    print("-" * 80)
    try:
        result = collector.get_whale_movements('BTC', threshold_usd=1_000_000)
        print(f"✅ BTC Whale Movements:")
        print(f"   Whale Buy Volume: {result['whale_buy_volume']:.2f}")
        print(f"   Whale Sell Volume: {result['whale_sell_volume']:.2f}")
        print(f"   Whale Net Flow: {result['whale_net_flow']:.2f}")
        print(f"   Large Trade Count: {result['large_trade_count']}")
    except Exception as e:
        print(f"❌ Error: {e}")
    print()
    
    # Test 5: Liquidity Metrics
    print("📊 TEST 5: Liquidity Metrics (Order Book)")
    print("-" * 80)
    try:
        result = collector.get_liquidity_metrics('BTCUSDT')
        print(f"✅ BTC Liquidity:")
        print(f"   Bid-Ask Spread: {result['bid_ask_spread']:.4f}%")
        print(f"   Volume Imbalance: {result['volume_imbalance']:.2f}")
        print(f"   Liquidity Score: {result['liquidity_score']:.2f}")
    except Exception as e:
        print(f"❌ Error: {e}")
    print()
    
    # Test 6: Funding Rate
    print("📊 TEST 6: Funding Rate (Futures)")
    print("-" * 80)
    try:
        result = collector.get_funding_rate('BTCUSDT')
        print(f"✅ BTC Funding Rate:")
        print(f"   Current: {result['funding_rate']:.6f}")
        print(f"   8h Average: {result['funding_rate_8h']:.6f}")
        print(f"   24h Average: {result['funding_rate_24h']:.6f}")
    except Exception as e:
        print(f"❌ Error: {e}")
    print()
    
    # Test 7: Composite Research Signal
    print("📊 TEST 7: Composite Research Signal")
    print("-" * 80)
    try:
        result = collector.calculate_research_signal('BTC')
        print(f"✅ BTC Research Signal:")
        print(f"   Research Signal: {result['research_signal']:.3f} (-1 bearish, +1 bullish)")
        print(f"   Signal Strength: {result['signal_strength']:.2f} (0-1, higher = stronger)")
        print(f"   Components:")
        print(f"     - Sentiment: {result['components']['sentiment']:.3f}")
        print(f"     - Fear & Greed: {result['components']['fear_greed']:.3f}")
        print(f"     - Whale Flow: {result['components']['whale_flow']:.3f}")
        print(f"     - Exchange Flow: {result['components']['exchange_flow']:.3f}")
        print(f"     - Funding Rate: {result['components']['funding_rate']:.3f}")
    except Exception as e:
        print(f"❌ Error: {e}")
    print()
    
    # Summary
    print("=" * 80)
    print("✅ TESTING COMPLETE")
    print("=" * 80)
    print()
    print("📝 SUMMARY:")
    print("  - If you see all ✅ above, the data collector is working correctly")
    print("  - If you see ❌, the API may be temporarily unavailable")
    print("  - Data is cached for 5 minutes (configurable)")
    print()
    print("🚀 NEXT STEPS:")
    print("  1. Update research_config.json with your API keys (if using paid APIs)")
    print("  2. Integrate with FreqAI strategies (Week 2)")
    print("  3. Test with backtesting (Week 3)")
    print()


def demo_signal_interpretation():
    """Demonstrate how to interpret the research signal"""
    print()
    print("=" * 80)
    print("RESEARCH SIGNAL INTERPRETATION GUIDE")
    print("=" * 80)
    print()
    print("Research Signal Range (-1 to +1):")
    print("  +1.0   →  Extremely Bullish (all indicators agree)")
    print("  +0.5   →  Moderately Bullish")
    print("   0.0   →  Neutral (mixed signals)")
    print("  -0.5   →  Moderately Bearish")
    print("  -1.0   →  Extremely Bearish (all indicators agree)")
    print()
    print("Signal Strength (0 to 1):")
    print("  High (0.7+)  →  High confidence (signals aligned)")
    print("  Medium (0.4-0.7) →  Moderate confidence")
    print("  Low (<0.4)   →  Low confidence (mixed signals)")
    print()
    print("Usage in Strategies:")
    print("  if research_signal > 0.3 AND signal_strength > 0.5:")
    print("      → Strong bullish confirmation → ENTER")
    print()
    print("  if whale_flow > 0 AND sentiment > 0 AND exchange_flow > 0:")
    print("      → All signals agree → HIGH CONVICTION")
    print()
    print("  if research_signal < -0.2 AND signal_strength > 0.6:")
    print("      → Strong bearish signal → EXIT or REDUCE POSITION")
    print()


if __name__ == "__main__":
    print()
    test_collector()
    demo_signal_interpretation()
