"""
Binance Research Data Loader - For Backtesting & HyperOpt Only
Fetches and prepares historical research data for backtest periods
Does NOT include live streaming (live bot is remote on Raspberry Pi)

Usage:
    loader = BinanceBacktestResearchLoader()
    research_df = loader.load_research_data('BTC', '2025-09-20', '2025-10-27')
    # Then merge into backtest dataframe
"""

import pandas as pd
import numpy as np
import requests
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class BinanceBacktestResearchLoader:
    """
    Load historical Binance research data for backtesting
    Fetches data once, caches locally to avoid repeated API calls
    """
    
    def __init__(self, cache_dir: str = '/home/bederf/freqtrade/user_data/research_data'):
        """
        Initialize the research data loader
        
        Args:
            cache_dir: Where to store/load cached research data
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
        self.binance_base = "https://api.binance.com/api/v3"
        self.coingecko_base = "https://api.coingecko.com/api/v3"
        self.request_timeout = 10
        
        logger.info(f"BinanceBacktestResearchLoader initialized with cache: {cache_dir}")
    
    # ==================== HISTORICAL WHALE FLOWS ====================
    
    def _fetch_exchange_flows_historical(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Calculate daily exchange flows (inflow - outflow)
        Uses historical trade data to estimate flows
        
        Args:
            symbol: 'BTC', 'ETH', etc
            start_date: '2025-09-20'
            end_date: '2025-10-27'
        
        Returns:
            DataFrame with columns: date, inflow, outflow, net_flow
        """
        try:
            pair = f"{symbol}USDT"
            
            # Get klines data for the period
            start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
            end_ts = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)
            
            # Binance API limit: 1000 candles per request
            interval_ms = 24 * 60 * 60 * 1000  # 1 day
            
            all_data = []
            current_ts = start_ts
            
            while current_ts < end_ts:
                try:
                    response = requests.get(
                        f"{self.binance_base}/klines",
                        params={
                            'symbol': pair,
                            'interval': '1d',
                            'startTime': current_ts,
                            'limit': 1000
                        },
                        timeout=self.request_timeout
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    if not data:
                        break
                    
                    all_data.extend(data)
                    current_ts = data[-1][0] + interval_ms
                    
                except Exception as e:
                    logger.warning(f"Error fetching klines for {pair}: {e}")
                    break
            
            # Parse into DataFrame
            if all_data:
                df = pd.DataFrame(
                    all_data,
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume',
                             'close_time', 'quote_asset_volume', 'trades', 'buy_base',
                             'buy_quote', 'ignore']
                )
                
                df['date'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms').dt.date
                
                # Estimate flows: buy_base is inflow, quote - buy_quote is outflow
                df['inflow'] = df['buy_base'].astype(float)
                df['outflow'] = (df['volume'].astype(float) - df['buy_base'].astype(float))
                df['net_flow'] = df['inflow'] - df['outflow']
                
                # Group by date
                daily = df.groupby('date').agg({
                    'inflow': 'sum',
                    'outflow': 'sum',
                    'net_flow': 'sum'
                }).reset_index()
                
                return daily
        
        except Exception as e:
            logger.error(f"Error fetching exchange flows: {e}")
        
        return pd.DataFrame()
    
    # ==================== HISTORICAL SENTIMENT ====================
    
    def _fetch_sentiment_historical(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Fetch historical sentiment data from CoinGecko
        Note: CoinGecko has limited historical sentiment data
        This returns daily market data as proxy
        
        Args:
            symbol: 'bitcoin', 'ethereum'
            start_date: '2025-09-20'
            end_date: '2025-10-27'
        
        Returns:
            DataFrame with sentiment proxy data
        """
        try:
            # Parse dates
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            
            # Coingecko market data endpoint
            # This gives us market cap change as sentiment proxy
            response = requests.get(
                f"{self.coingecko_base}/coins/{symbol}/market_chart",
                params={
                    'vs_currency': 'usd',
                    'days': (end - start).days,
                    'interval': 'daily'
                },
                timeout=self.request_timeout
            )
            response.raise_for_status()
            data = response.json()
            
            prices = data['prices']
            market_caps = data['market_caps']
            
            # Convert to DataFrame
            df = pd.DataFrame({
                'timestamp': [int(p[0]) for p in prices],
                'price': [p[1] for p in prices],
                'market_cap': [m[1] for m in market_caps]
            })
            
            df['date'] = pd.to_datetime(df['timestamp'], unit='ms').dt.date
            
            # Calculate sentiment proxies
            df['price_change_pct'] = df['price'].pct_change() * 100
            df['market_cap_change_pct'] = df['market_cap'].pct_change() * 100
            
            # Normalize to -1 to +1 range
            df['sentiment_score'] = df['price_change_pct'].rolling(7).mean() / 10
            df['sentiment_score'] = np.clip(df['sentiment_score'], -1, 1)
            
            return df[['date', 'price', 'sentiment_score', 'price_change_pct']]
        
        except Exception as e:
            logger.error(f"Error fetching sentiment: {e}")
        
        return pd.DataFrame()
    
    # ==================== HISTORICAL FUNDING RATES ====================
    
    def _fetch_funding_rates_historical(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Fetch historical funding rates from Binance Futures
        Shows leverage sentiment (positive = long bias)
        
        Args:
            symbol: 'BTCUSDT', 'ETHUSDT'
            start_date: '2025-09-20'
            end_date: '2025-10-27'
        
        Returns:
            DataFrame with daily average funding rates
        """
        try:
            start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
            end_ts = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)
            
            all_funding = []
            current_ts = start_ts
            
            while current_ts < end_ts:
                try:
                    response = requests.get(
                        "https://fapi.binance.com/fapi/v1/fundingRate",
                        params={
                            'symbol': symbol,
                            'startTime': current_ts,
                            'limit': 1000
                        },
                        timeout=self.request_timeout
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    if not data:
                        break
                    
                    all_funding.extend(data)
                    current_ts = int(data[-1]['fundingTime']) + 1
                
                except Exception as e:
                    logger.warning(f"Error fetching funding rates: {e}")
                    break
            
            if all_funding:
                df = pd.DataFrame(all_funding)
                df['timestamp'] = df['fundingTime'].astype(int)
                df['date'] = pd.to_datetime(df['timestamp'], unit='ms').dt.date
                df['funding_rate'] = df['fundingRate'].astype(float)
                
                # Daily average
                daily = df.groupby('date').agg({
                    'funding_rate': 'mean'
                }).reset_index()
                
                daily['funding_rate_pct'] = daily['funding_rate'] * 100
                
                return daily
        
        except Exception as e:
            logger.error(f"Error fetching funding rates: {e}")
        
        return pd.DataFrame()
    
    # ==================== FEAR & GREED INDEX ====================
    
    def _fetch_fear_greed_historical(
        self,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Fetch historical Fear & Greed Index
        
        Args:
            start_date: '2025-09-20'
            end_date: '2025-10-27'
        
        Returns:
            DataFrame with daily fear/greed values
        """
        try:
            response = requests.get(
                "https://api.alternative.me/fng/",
                params={'limit': 0},  # Get all available data
                timeout=self.request_timeout
            )
            response.raise_for_status()
            data = response.json()
            
            if data['data']:
                df = pd.DataFrame(data['data'])
                df['date'] = pd.to_datetime(df['timestamp'].astype(int), unit='s').dt.date
                df['fear_greed'] = df['value'].astype(int)
                
                # Filter by date range
                start = pd.to_datetime(start_date).date()
                end = pd.to_datetime(end_date).date()
                
                df = df[(df['date'] >= start) & (df['date'] <= end)]
                
                return df[['date', 'fear_greed']]
        
        except Exception as e:
            logger.error(f"Error fetching fear/greed index: {e}")
        
        return pd.DataFrame()
    
    # ==================== LOAD/CACHE MANAGEMENT ====================
    
    def load_research_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        use_cache: bool = True,
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """
        Load research data for a symbol and date range
        Tries cache first, then fetches from APIs if needed
        
        Args:
            symbol: 'BTC', 'ETH'
            start_date: '2025-09-20'
            end_date: '2025-10-27'
            use_cache: Use cached data if available
            force_refresh: Ignore cache and fetch fresh data
        
        Returns:
            DataFrame with columns: date, exchange_inflow, exchange_outflow,
                                  net_flow, sentiment_score, funding_rate, fear_greed
        """
        cache_file = os.path.join(
            self.cache_dir,
            f"{symbol}_{start_date}_{end_date}_research.csv"
        )
        
        # Try cache first
        if use_cache and not force_refresh and os.path.exists(cache_file):
            logger.info(f"Loading cached research data from {cache_file}")
            return pd.read_csv(cache_file)
        
        logger.info(f"Fetching fresh research data for {symbol} ({start_date} to {end_date})")
        
        # Fetch all data sources
        exchange_flows = self._fetch_exchange_flows_historical(symbol, start_date, end_date)
        sentiment = self._fetch_sentiment_historical(symbol.lower(), start_date, end_date)
        funding = self._fetch_funding_rates_historical(f"{symbol}USDT", start_date, end_date)
        fear_greed = self._fetch_fear_greed_historical(start_date, end_date)
        
        # Merge on date
        result = pd.DataFrame({
            'date': pd.date_range(start_date, end_date, freq='D').date
        })
        
        if not exchange_flows.empty:
            result = result.merge(exchange_flows, on='date', how='left')
        
        if not sentiment.empty:
            result = result.merge(sentiment[['date', 'sentiment_score']], on='date', how='left')
        
        if not funding.empty:
            result = result.merge(funding, on='date', how='left')
        
        if not fear_greed.empty:
            result = result.merge(fear_greed, on='date', how='left')
        
        # Fill missing values (Fixed: fillna(method='ffill') deprecated in pandas 2.x)
        result = result.ffill().fillna(0)
        
        # Save to cache
        result.to_csv(cache_file, index=False)
        logger.info(f"Cached research data to {cache_file}")
        
        return result
    
    def get_research_features_for_candle(
        self,
        candle_date: datetime,
        symbol: str,
        research_data: pd.DataFrame
    ) -> Dict[str, float]:
        """
        Get research features for a specific candle
        Used during backtest populate_indicators()

        Args:
            candle_date: Candle timestamp (datetime or date)
            symbol: Trading symbol
            research_data: Research dataframe loaded from load_research_data()

        Returns:
            Dict with research features
        """
        try:
            # Handle both datetime and date objects
            if hasattr(candle_date, 'date') and callable(candle_date.date):
                date = candle_date.date()
            else:
                date = candle_date
            
            # Find matching row
            row = research_data[research_data['date'] == date]
            
            if row.empty:
                # Return neutral values
                return {
                    'research_exchange_inflow': 0,
                    'research_exchange_outflow': 0,
                    'research_net_flow': 0,
                    'research_sentiment': 0,
                    'research_funding_rate': 0,
                    'research_fear_greed': 50
                }
            
            row = row.iloc[0]
            
            return {
                'research_exchange_inflow': float(row.get('inflow', 0)),
                'research_exchange_outflow': float(row.get('outflow', 0)),
                'research_net_flow': float(row.get('net_flow', 0)),
                'research_sentiment': float(row.get('sentiment_score', 0)),
                'research_funding_rate': float(row.get('funding_rate_pct', 0)),
                'research_fear_greed': float(row.get('fear_greed', 50))
            }
        
        except Exception as e:
            logger.error(f"Error getting research features: {e}")
            return {
                'research_exchange_inflow': 0,
                'research_exchange_outflow': 0,
                'research_net_flow': 0,
                'research_sentiment': 0,
                'research_funding_rate': 0,
                'research_fear_greed': 50
            }


# ==================== USAGE IN STRATEGY ====================

"""
To use in your strategy:

from binance_research_backtest_loader import BinanceBacktestResearchLoader

class LeaFreqAIStrategy(IStrategy):
    
    def __init__(self, config):
        super().__init__(config)
        self.research_loader = BinanceBacktestResearchLoader()
        self.research_data = {}
    
    def populate_indicators(self, dataframe, metadata):
        # Load research data once per pair
        pair = metadata['pair']
        if pair not in self.research_data:
            symbol = pair.split('/')[0]  # 'BTC' from 'BTC/USDT'
            self.research_data[pair] = self.research_loader.load_research_data(
                symbol,
                '2025-09-20',
                '2025-10-27'
            )
        
        # Add research features to each row
        research_df = self.research_data[pair]
        for idx, row in dataframe.iterrows():
            features = self.research_loader.get_research_features_for_candle(
                row['date'],
                symbol,
                research_df
            )
            for key, value in features.items():
                dataframe.loc[idx, key] = value
        
        # Now you can use these features in your entry logic:
        # dataframe['enter_long'] = (
        #     (dataframe['&-target'] > 0.005) &  # ML signal
        #     (dataframe['research_net_flow'] > 0) &  # Whale accumulation
        #     (dataframe['research_sentiment'] > 0.2)  # Bullish sentiment
        # )
        
        return dataframe
"""

if __name__ == "__main__":
    # Test the loader
    loader = BinanceBacktestResearchLoader()
    
    print("Loading research data for BTC...")
    btc_research = loader.load_research_data('BTC', '2025-09-20', '2025-10-27')
    print(f"\nLoaded {len(btc_research)} days of research data")
    print("\nColumns:", btc_research.columns.tolist())
    print("\nFirst 5 rows:")
    print(btc_research.head())
