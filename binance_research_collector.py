"""
Binance Research Data Collector
Fetches on-chain metrics, sentiment, liquidity, and fundamental data
for FreqAI enhancement

Supports:
- Binance API (price, volume, real-time)
- CoinGecko API (market data, sentiment)
- Alternative.me (Fear & Greed Index)
- Glassnode API (on-chain metrics) - optional
- Santiment API (social sentiment) - optional
"""

import logging
import pandas as pd
import numpy as np
import requests
import time
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
from functools import lru_cache
import json
import os

logger = logging.getLogger(__name__)


class BinanceResearchCollector:
    """
    Main collector for Binance research data
    Aggregates multiple data sources for strategy enhancement
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the research data collector
        
        Args:
            config: Configuration dict with API keys and settings
                {
                    'binance_api_key': 'your_key',
                    'binance_api_secret': 'your_secret',
                    'coingecko_api_key': 'free_or_pro_key',
                    'glassnode_api_key': 'optional',
                    'santiment_api_key': 'optional',
                    'cache_dir': '/path/to/cache',
                    'cache_ttl': 300,  # seconds
                }
        """
        self.config = config or {}
        self.cache_dir = self.config.get('cache_dir', '/tmp/research_cache')
        self.cache_ttl = self.config.get('cache_ttl', 300)  # 5 minutes default
        self.request_timeout = 10
        self.max_retries = 3
        
        # Create cache directory
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # API endpoints
        self.binance_base = "https://api.binance.com/api/v3"
        self.coingecko_base = "https://api.coingecko.com/api/v3"
        self.glassnode_base = "https://api.glassnode.com/v1"
        self.santiment_base = "https://api.santiment.net/graphql"
        self.alternative_me_url = "https://api.alternative.me/fng/"
        
        logger.info("BinanceResearchCollector initialized")
    
    # ==================== FEAR & GREED INDEX ====================
    
    def get_fear_greed_index(self) -> Dict[str, Any]:
        """
        Fetch Fear & Greed Index from Alternative.me (FREE)
        
        Returns:
            {
                'fear_greed_value': 0-100,
                'fear_greed_classification': 'Extreme Greed' | 'Greed' | 'Fear' | 'Extreme Fear',
                'timestamp': datetime
            }
        """
        try:
            cache_key = 'fear_greed_index'
            cached = self._get_cache(cache_key)
            if cached:
                return cached
            
            response = requests.get(
                self.alternative_me_url,
                timeout=self.request_timeout,
                params={'limit': 1, 'format': 'json'}
            )
            response.raise_for_status()
            data = response.json()
            
            if data['data']:
                latest = data['data'][0]
                result = {
                    'fear_greed_value': float(latest['value']),
                    'fear_greed_classification': latest['value_classification'],
                    'timestamp': datetime.fromtimestamp(int(latest['timestamp']))
                }
                self._set_cache(cache_key, result)
                return result
        except Exception as e:
            logger.error(f"Error fetching Fear & Greed Index: {e}")
            return {'fear_greed_value': 50, 'fear_greed_classification': 'Neutral', 'timestamp': datetime.now()}
    
    # ==================== COINGECKO SENTIMENT ====================
    
    def get_coingecko_sentiment(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch sentiment data from CoinGecko (FREE tier available)
        
        Args:
            symbol: Coin ID (e.g., 'bitcoin', 'ethereum')
        
        Returns:
            {
                'sentiment_votes_up': percentage,
                'sentiment_votes_down': percentage,
                'market_cap_change_24h': percentage,
                'volume_change_24h': percentage,
            }
        """
        try:
            cache_key = f'coingecko_sentiment_{symbol}'
            cached = self._get_cache(cache_key)
            if cached:
                return cached
            
            response = requests.get(
                f"{self.coingecko_base}/coins/{symbol}",
                timeout=self.request_timeout,
                params={
                    'localization': 'false',
                    'tickers': 'false',
                    'market_data': 'true',
                    'community_data': 'true',
                    'developer_data': 'false'
                }
            )
            response.raise_for_status()
            data = response.json()
            
            result = {
                'sentiment_votes_up': data.get('sentiment_votes_up_percentage', 50),
                'sentiment_votes_down': data.get('sentiment_votes_down_percentage', 50),
                'market_cap_change_24h': data.get('market_data', {}).get('market_cap_change_percentage_24h', 0),
                'volume_change_24h': data.get('market_data', {}).get('total_volume', {}).get('percentage_change_24h', 0),
            }
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error(f"Error fetching CoinGecko sentiment for {symbol}: {e}")
            return {'sentiment_votes_up': 50, 'sentiment_votes_down': 50, 'market_cap_change_24h': 0, 'volume_change_24h': 0}
    
    # ==================== EXCHANGE FLOWS ====================
    
    def get_exchange_flows(self, symbol: str = 'BTC') -> Dict[str, float]:
        """
        Calculate exchange flows from Binance orderbook and volume
        This is a simplified approximation without Glassnode
        
        Args:
            symbol: Trading symbol (BTC, ETH, etc)
        
        Returns:
            {
                'exchange_inflow': estimated inflow,
                'exchange_outflow': estimated outflow,
                'net_flow': inflow - outflow,
                'timestamp': datetime
            }
        """
        try:
            cache_key = f'exchange_flows_{symbol}'
            cached = self._get_cache(cache_key, ttl=600)  # 10 min cache
            if cached:
                return cached
            
            # Get recent trades from Binance
            pair = f"{symbol}USDT"
            response = requests.get(
                f"{self.binance_base}/trades",
                timeout=self.request_timeout,
                params={'symbol': pair, 'limit': 500}
            )
            response.raise_for_status()
            trades = response.json()
            
            # Calculate buy/sell volume (buy = inflow, sell = outflow)
            buy_volume = sum(float(t['qty']) for t in trades if not t['isBuyerMaker'])
            sell_volume = sum(float(t['qty']) for t in trades if t['isBuyerMaker'])
            
            result = {
                'exchange_inflow': buy_volume,
                'exchange_outflow': sell_volume,
                'net_flow': buy_volume - sell_volume,
                'timestamp': datetime.now()
            }
            self._set_cache(cache_key, result, ttl=600)
            return result
        except Exception as e:
            logger.error(f"Error fetching exchange flows for {symbol}: {e}")
            return {'exchange_inflow': 0, 'exchange_outflow': 0, 'net_flow': 0, 'timestamp': datetime.now()}
    
    # ==================== WHALE MOVEMENTS ====================
    
    def get_whale_movements(self, symbol: str = 'BTC', threshold_usd: float = 1_000_000) -> Dict[str, Any]:
        """
        Detect large transactions (whale movements)
        Simplified implementation - uses trading volume as proxy
        
        Args:
            symbol: Coin symbol
            threshold_usd: Minimum transaction size to track
        
        Returns:
            {
                'whale_buy_volume': estimated whale buys,
                'whale_sell_volume': estimated whale sells,
                'whale_net_flow': net whale flow,
                'large_trade_count': number of large trades,
            }
        """
        try:
            cache_key = f'whale_movements_{symbol}'
            cached = self._get_cache(cache_key, ttl=600)
            if cached:
                return cached
            
            pair = f"{symbol}USDT"
            response = requests.get(
                f"{self.binance_base}/trades",
                timeout=self.request_timeout,
                params={'symbol': pair, 'limit': 1000}
            )
            response.raise_for_status()
            trades = response.json()
            
            # Get current price for USD conversion
            ticker = requests.get(
                f"{self.binance_base}/ticker/price",
                timeout=self.request_timeout,
                params={'symbol': pair}
            ).json()
            price = float(ticker['price'])
            
            # Find whale trades (>$1M or configurable)
            whale_trades = [
                t for t in trades 
                if float(t['qty']) * price > threshold_usd
            ]
            
            whale_buys = sum(float(t['qty']) for t in whale_trades if not t['isBuyerMaker'])
            whale_sells = sum(float(t['qty']) for t in whale_trades if t['isBuyerMaker'])
            
            result = {
                'whale_buy_volume': whale_buys,
                'whale_sell_volume': whale_sells,
                'whale_net_flow': whale_buys - whale_sells,
                'large_trade_count': len(whale_trades),
            }
            self._set_cache(cache_key, result, ttl=600)
            return result
        except Exception as e:
            logger.error(f"Error fetching whale movements for {symbol}: {e}")
            return {'whale_buy_volume': 0, 'whale_sell_volume': 0, 'whale_net_flow': 0, 'large_trade_count': 0}
    
    # ==================== LIQUIDITY METRICS ====================
    
    def get_liquidity_metrics(self, symbol: str) -> Dict[str, float]:
        """
        Get liquidity metrics from order book
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
        
        Returns:
            {
                'bid_ask_spread': spread percentage,
                'volume_imbalance': buy_vol / total_vol,
                'liquidity_score': 0-1 (higher = more liquid),
            }
        """
        try:
            cache_key = f'liquidity_{symbol}'
            cached = self._get_cache(cache_key, ttl=300)
            if cached:
                return cached
            
            # Get order book
            response = requests.get(
                f"{self.binance_base}/depth",
                timeout=self.request_timeout,
                params={'symbol': symbol, 'limit': 100}
            )
            response.raise_for_status()
            orderbook = response.json()
            
            bids = orderbook['bids']
            asks = orderbook['asks']
            
            # Calculate spread
            best_bid = float(bids[0][0]) if bids else 0
            best_ask = float(asks[0][0]) if asks else 0
            spread = ((best_ask - best_bid) / best_bid * 100) if best_bid > 0 else 0
            
            # Calculate volume imbalance
            bid_volume = sum(float(b[1]) for b in bids)
            ask_volume = sum(float(a[1]) for a in asks)
            total_volume = bid_volume + ask_volume
            imbalance = bid_volume / total_volume if total_volume > 0 else 0.5
            
            # Liquidity score (inverse of spread, normalized)
            liquidity = 1.0 / (1.0 + spread / 100.0)
            
            result = {
                'bid_ask_spread': spread,
                'volume_imbalance': imbalance,
                'liquidity_score': liquidity,
            }
            self._set_cache(cache_key, result, ttl=300)
            return result
        except Exception as e:
            logger.error(f"Error fetching liquidity metrics for {symbol}: {e}")
            return {'bid_ask_spread': 0.1, 'volume_imbalance': 0.5, 'liquidity_score': 0.8}
    
    # ==================== FUNDING RATES ====================
    
    def get_funding_rate(self, symbol: str) -> Dict[str, float]:
        """
        Get futures funding rate from Binance
        
        Args:
            symbol: Futures trading pair (e.g., 'BTCUSDT')
        
        Returns:
            {
                'funding_rate': current funding rate,
                'funding_rate_8h': 8-hour average,
                'funding_rate_24h': 24-hour average,
            }
        """
        try:
            cache_key = f'funding_rate_{symbol}'
            cached = self._get_cache(cache_key, ttl=3600)  # 1 hour
            if cached:
                return cached
            
            # Get current funding rate
            response = requests.get(
                "https://fapi.binance.com/fapi/v1/fundingRate",
                timeout=self.request_timeout,
                params={'symbol': symbol, 'limit': 100}
            )
            response.raise_for_status()
            funding_data = response.json()
            
            if funding_data:
                current = float(funding_data[-1]['fundingRate'])
                avg_8h = np.mean([float(f['fundingRate']) for f in funding_data[-8:]]) if len(funding_data) >= 8 else current
                avg_24h = np.mean([float(f['fundingRate']) for f in funding_data[-24:]]) if len(funding_data) >= 24 else current
                
                result = {
                    'funding_rate': current,
                    'funding_rate_8h': avg_8h,
                    'funding_rate_24h': avg_24h,
                }
                self._set_cache(cache_key, result, ttl=3600)
                return result
        except Exception as e:
            logger.error(f"Error fetching funding rate for {symbol}: {e}")
        
        return {'funding_rate': 0.0, 'funding_rate_8h': 0.0, 'funding_rate_24h': 0.0}
    
    # ==================== COMPOSITE RESEARCH SIGNAL ====================
    
    def calculate_research_signal(
        self, 
        symbol: str,
        weights: Dict[str, float] = None
    ) -> Dict[str, Any]:
        """
        Calculate composite research signal combining all data sources
        
        Args:
            symbol: Trading symbol
            weights: Custom weights for different signals
                {
                    'sentiment': 0.3,
                    'whale_flow': 0.3,
                    'exchange_flow': 0.2,
                    'liquidity': 0.1,
                    'funding': 0.1,
                }
        
        Returns:
            {
                'research_signal': -1 to +1 (bearish to bullish),
                'signal_strength': 0-1 (confidence level),
                'components': {individual signals}
            }
        """
        if weights is None:
            weights = {
                'sentiment': 0.3,
                'whale_flow': 0.3,
                'exchange_flow': 0.2,
                'liquidity': 0.1,
                'funding': 0.1,
            }
        
        # Fetch all data
        fear_greed = self.get_fear_greed_index()
        sentiment = self.get_coingecko_sentiment(symbol.lower())
        whale = self.get_whale_movements(symbol)
        exchange = self.get_exchange_flows(symbol)
        funding = self.get_funding_rate(f"{symbol}USDT")
        
        # Normalize signals to -1 to +1
        # Sentiment: convert 0-100 to -1 to +1
        sentiment_score = (sentiment['sentiment_votes_up'] - 50) / 50
        
        # Fear & Greed: convert 0-100 to -1 to +1
        fear_greed_score = (fear_greed['fear_greed_value'] - 50) / 50
        
        # Whale flow: normalize
        total_whale = whale['whale_buy_volume'] + whale['whale_sell_volume']
        whale_score = (whale['whale_buy_volume'] - whale['whale_sell_volume']) / max(total_whale, 1)
        
        # Exchange flow: normalize
        total_exchange = exchange['exchange_inflow'] + exchange['exchange_outflow']
        exchange_score = (exchange['exchange_inflow'] - exchange['exchange_outflow']) / max(total_exchange, 1)
        
        # Funding rate: positive = bullish (more long positions)
        funding_score = np.clip(funding['funding_rate'] * 100, -1, 1)
        
        # Composite signal
        research_signal = (
            weights['sentiment'] * (sentiment_score + fear_greed_score) / 2 +
            weights['whale_flow'] * whale_score +
            weights['exchange_flow'] * exchange_score +
            weights['liquidity'] * 0.0 +  # Liquidity doesn't have directional bias
            weights['funding'] * funding_score
        )
        
        # Signal strength (how many signals agree)
        signals = [
            abs(sentiment_score),
            abs(whale_score),
            abs(exchange_score),
            abs(funding_score)
        ]
        signal_strength = np.mean(signals)
        
        return {
            'research_signal': np.clip(research_signal, -1, 1),
            'signal_strength': signal_strength,
            'components': {
                'sentiment': sentiment_score,
                'fear_greed': fear_greed_score,
                'whale_flow': whale_score,
                'exchange_flow': exchange_score,
                'funding_rate': funding_score,
            },
            'timestamp': datetime.now()
        }
    
    # ==================== CACHING ====================
    
    def _get_cache(self, key: str, ttl: Optional[int] = None) -> Optional[Any]:
        """Get cached data if not expired"""
        if ttl is None:
            ttl = self.cache_ttl
        
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(cache_file):
            stat = os.stat(cache_file)
            age = time.time() - stat.st_mtime
            if age < ttl:
                try:
                    with open(cache_file, 'r') as f:
                        return json.load(f)
                except Exception as e:
                    logger.warning(f"Cache read error: {e}")
        return None
    
    def _set_cache(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        """Cache data to file"""
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        try:
            # Convert datetime objects to ISO format
            json_data = json.dumps(data, default=str)
            with open(cache_file, 'w') as f:
                f.write(json_data)
        except Exception as e:
            logger.warning(f"Cache write error: {e}")
    
    def clear_cache(self, pattern: Optional[str] = None) -> None:
        """Clear cache files"""
        if pattern is None:
            pattern = "*"
        
        import glob
        cache_files = glob.glob(os.path.join(self.cache_dir, f"{pattern}.json"))
        for f in cache_files:
            try:
                os.remove(f)
                logger.info(f"Cleared cache: {f}")
            except Exception as e:
                logger.error(f"Error clearing cache: {e}")


# ==================== OPTIONAL: ADVANCED APIS ====================

class GlassnodeDataCollector:
    """
    Glassnode API integration for advanced on-chain metrics
    Requires paid API key ($25-500/month)
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.glassnode.com/v1"
    
    def get_mvrv_ratio(self, symbol: str = 'btc') -> float:
        """Market Value vs Realized Value ratio"""
        # Implementation would go here
        pass
    
    def get_sopr_ratio(self, symbol: str = 'btc') -> float:
        """Spent Output Profit Ratio"""
        # Implementation would go here
        pass
    
    def get_exchange_reserve(self, symbol: str = 'btc') -> float:
        """Total exchange reserve"""
        # Implementation would go here
        pass


class SantimentDataCollector:
    """
    Santiment API integration for social sentiment
    Requires API key ($25-200/month)
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.santiment.net/graphql"
    
    def get_social_sentiment(self, asset: str) -> float:
        """Social media sentiment score"""
        # Implementation would go here
        pass
    
    def get_twitter_sentiment(self, asset: str) -> float:
        """Twitter-specific sentiment"""
        # Implementation would go here
        pass


if __name__ == "__main__":
    # Test the collector
    collector = BinanceResearchCollector()
    
    # Test Fear & Greed
    print("Fear & Greed Index:", collector.get_fear_greed_index())
    
    # Test sentiment
    print("Bitcoin Sentiment:", collector.get_coingecko_sentiment('bitcoin'))
    
    # Test exchange flows
    print("BTC Exchange Flows:", collector.get_exchange_flows('BTC'))
    
    # Test whale movements
    print("BTC Whale Movements:", collector.get_whale_movements('BTC'))
    
    # Test liquidity
    print("BTC Liquidity:", collector.get_liquidity_metrics('BTCUSDT'))
    
    # Test funding rate
    print("BTC Funding Rate:", collector.get_funding_rate('BTCUSDT'))
    
    # Test composite signal
    print("BTC Research Signal:", collector.calculate_research_signal('BTC'))
