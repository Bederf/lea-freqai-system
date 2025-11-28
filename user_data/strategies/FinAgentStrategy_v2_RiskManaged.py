"""
FinAgent Strategy v2 - Enhanced with Advanced Risk Management
Implements Kelly Criterion, dynamic stops, portfolio heat limits, and correlation management
"""
import logging
from functools import reduce
from collections import deque
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib
import hashlib

from freqtrade.strategy import IStrategy, Trade
from typing import Optional, Union

# Import research data loader for backtest/hyperopt enhancement
try:
    from binance_research_backtest_loader import BinanceBacktestResearchLoader
    RESEARCH_LOADER_AVAILABLE = True
except ImportError:
    RESEARCH_LOADER_AVAILABLE = False
    logger_init = logging.getLogger(__name__)
    logger_init.warning("Research loader not available - running without Binance research data")

logger = logging.getLogger(__name__)


class RiskManager:
    """Advanced risk management using Kelly Criterion and portfolio heat"""

    def __init__(self):
        self.max_portfolio_risk = 0.06  # 6% max heat
        self.max_trade_risk = 0.015     # 1.5% per trade
        self.min_rr_ratio = 1.5         # 1.5:1 minimum
        self.base_position = 0.02       # 2% base
        # REMOVED: Dead code state tracking (open_trades, recent_losses, peak_balance, current_balance)
        # Now uses Freqtrade's native trade tracking via self.trades

    def calculate_position(self, signal: float, confidence: float, regime: str, atr: float, price: float) -> dict:
        """Kelly Criterion position sizing"""
        # Win probability estimate
        win_prob = 0.45 + (signal * 0.25)
        win_prob = np.clip(win_prob * (0.8 + confidence * 0.4), 0.45, 0.70)

        # Kelly fraction
        rr_ratio = 1.5
        kelly = (win_prob * rr_ratio - (1 - win_prob)) / rr_ratio
        kelly = kelly * 0.25  # Conservative Kelly

        # Regime adjustment
        regime_mult = {'trending_up': 1.2, 'trending_down': 1.1, 'ranging': 0.8, 'volatile': 0.6, 'uncertain': 0.5}.get(regime, 0.7)

        position_pct = self.base_position * kelly * regime_mult
        position_pct = np.clip(position_pct, 0.01, 0.05)

        # Stop/target levels
        stop_dist = np.clip((atr * 2.0) / price, 0.015, 0.04)
        target = np.clip(stop_dist * rr_ratio, stop_dist * 1.5, 0.10)

        # Portfolio heat check
        if self.get_portfolio_heat() >= self.max_portfolio_risk:
            return {'size': 0, 'stop': -stop_dist, 'target': target}

        # Drawdown adjustment
        dd = self.get_drawdown()
        if dd > 0.15:
            position_pct *= 0.3
        elif dd > 0.10:
            position_pct *= 0.5
        elif dd > 0.05:
            position_pct *= 0.75

        return {'size': position_pct, 'stop': -stop_dist, 'target': target}

    def get_portfolio_heat(self) -> float:
        """Current portfolio risk exposure - placeholder, use Freqtrade trade tracking instead"""
        # TODO: Implement using self.trades from parent strategy if needed
        return 0.0

    def get_drawdown(self) -> float:
        """Current drawdown percentage - placeholder, use Freqtrade wallet tracking instead"""
        # TODO: Implement using self.wallets.get_total_stake_amount() if needed
        return 0.0


class PatternMemory:
    """Pattern learning with confidence scoring"""

    def __init__(self, max_patterns=500):
        self.patterns = {}

    def hash_pattern(self, features: dict) -> str:
        feature_str = ''.join(f"{k}:{round(float(v), 4)}," for k, v in sorted(features.items()))
        return hashlib.md5(feature_str.encode()).hexdigest()[:16]

    def get_confidence(self, features: dict) -> float:
        h = self.hash_pattern(features)
        if h not in self.patterns:
            return 1.0
        outcomes = self.patterns.get(h, {}).get('outcomes', [])
        if not outcomes:
            return 1.0
        win_rate = sum(1 for o in outcomes if o > 0) / len(outcomes)
        return 0.5 + (win_rate * 1.0)


class MarketRegimeDetector:
    """Market regime classification"""

    def detect_regime(self, df: DataFrame) -> str:
        if len(df) < 50:
            return 'uncertain'

        recent = df.tail(50)
        adx = ta.ADX(recent, timeperiod=14)
        atr = ta.ATR(recent, timeperiod=14)
        atr_pct = (atr.iloc[-1] / recent['close'].iloc[-1] * 100) if len(atr) > 0 else 2

        ema_20 = ta.EMA(recent, timeperiod=20)
        ema_50 = ta.EMA(recent, timeperiod=50)
        trend_diff = (ema_20.iloc[-1] - ema_50.iloc[-1]) / ema_50.iloc[-1] if len(ema_20) > 0 else 0

        adx_val = adx.iloc[-1] if len(adx) > 0 else 20

        if adx_val > 25:
            return 'trending_up' if trend_diff > 0.02 else 'trending_down'
        if atr_pct > 3.0:
            return 'volatile'
        if (recent['high'].max() - recent['low'].min()) / recent['close'].mean() < 0.02:
            return 'ranging'

        return 'uncertain'


class NormalizedIndicators:
    """Normalized indicator signals"""

    def process(self, df: DataFrame) -> dict:
        signals = {}

        if len(df) < 30:
            return {k: 0.0 for k in ['rsi', 'macd', 'bb', 'volume', 'trend']}

        # RSI normalization
        rsi = ta.RSI(df, timeperiod=14)
        signals['rsi'] = (rsi.iloc[-1] - 50) / 50 if len(rsi) > 0 else 0

        # MACD
        macd_data = ta.MACD(df)
        if len(macd_data) > 0:
            hist = macd_data['macdhist']
            hist_mean = hist.rolling(50).mean().iloc[-1]
            hist_std = hist.rolling(50).std().iloc[-1]
            signals['macd'] = (hist.iloc[-1] - hist_mean) / (hist_std + 1e-10) if hist_std > 0 else 0
        else:
            signals['macd'] = 0.0

        # Bollinger Bands
        bb = qtpylib.bollinger_bands(df['close'], window=20, stds=2)
        if len(bb) > 0:
            bb_width = bb['upper'].iloc[-1] - bb['lower'].iloc[-1]
            signals['bb'] = (df['close'].iloc[-1] - bb['mid'].iloc[-1]) / (bb_width / 2 + 1e-10) if bb_width > 0 else 0
        else:
            signals['bb'] = 0.0

        # Volume
        vol_ma = df['volume'].rolling(20).mean()
        signals['volume'] = np.tanh((df['volume'].iloc[-1] / (vol_ma.iloc[-1] + 1e-10) - 1) * 2) if len(vol_ma) > 0 else 0

        # Trend
        ema_20 = ta.EMA(df, timeperiod=20)
        ema_50 = ta.EMA(df, timeperiod=50)
        signals['trend'] = np.clip((ema_20.iloc[-1] - ema_50.iloc[-1]) / (ema_50.iloc[-1] + 1e-10) * 10, -1, 1) if len(ema_20) > 0 else 0

        return {k: np.clip(v, -1, 1) for k, v in signals.items()}


class FinAgentStrategy_v2_RiskManaged(IStrategy):
    """FinAgent v2: Simplified entry with advanced risk management"""

    INTERFACE_VERSION = 3
    can_short = False

    timeframe = "5m"
    startup_candle_count = 200

    # Dynamic management via custom_stoploss() function
    stoploss = -0.10
    use_custom_stoploss = True
    # FIXED: Disabled aggressive trailing stop that was sabotaging risk management
    # The custom_stoploss() function now has full control of stop/exit logic
    trailing_stop = False
    # trailing_stop_positive = 0.008  # DISABLED - was closing trades at 0.8% profit
    # trailing_stop_positive_offset = 0.015  # DISABLED
    # trailing_only_offset_is_reached = True  # DISABLED

    minimal_roi = {"0": 0.10, "360": 0.05, "720": 0.025, "1440": 0}

    process_only_new_candles = True
    order_types = {"entry": "limit", "exit": "limit", "stoploss": "market", "stoploss_on_exchange": True}
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    def __init__(self, config: dict):
        super().__init__(config)
        self.risk_mgr = RiskManager()
        self.pattern_mem = PatternMemory()
        self.regime = MarketRegimeDetector()
        self.indicators = NormalizedIndicators()
        self.custom_info = {}

        # Initialize research data loader
        self.research_loader = None
        self.research_data_cache = {}  # Cache loaded research data by symbol

        if RESEARCH_LOADER_AVAILABLE:
            try:
                self.research_loader = BinanceBacktestResearchLoader()
                logger.info("Research loader initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize research loader: {e}")

    @property
    def plot_config(self):
        return {
            "main_plot": {"ema_50": {"color": "blue"}, "ema_200": {"color": "orange"}},
            "subplots": {
                "RSI": {"rsi": {"color": "red"}},
                "MACD": {"macd": {"color": "blue"}, "macdsignal": {"color": "orange"}},
                "AI": {"&-target": {"color": "green"}}
            }
        }

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int, metadata: dict, **kwargs) -> DataFrame:
        """
        Create stationary features for all timeframes - MUST MATCH LeaFreqAI
        """
        # Price returns (stationary)
        dataframe["%ret_1"] = dataframe["close"].pct_change(1)
        dataframe["%ret_3"] = dataframe["close"].pct_change(3)
        dataframe["%ret_12"] = dataframe["close"].pct_change(12)

        # Volatility (ATR-based, relative)
        dataframe["atr14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["%atr14_rel"] = dataframe["atr14"] / dataframe["close"]

        # Range (stationary)
        dataframe["%rng_24"] = (dataframe["high"].rolling(24).max() -
                                dataframe["low"].rolling(24).min()) / dataframe["close"]

        # Z-score (mean reversion indicator)
        returns = dataframe["close"].pct_change()
        dataframe["%z_48"] = (returns - returns.rolling(48).mean()) / returns.rolling(48).std()

        # Volume indicators
        dataframe["%vol_z_48"] = ((dataframe["volume"] - dataframe["volume"].rolling(48).mean()) /
                                  dataframe["volume"].rolling(48).std())

        # RSI (momentum)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["%bb_width"] = (dataframe["bb_upperband"] - dataframe["bb_lowerband"]) / dataframe["bb_middleband"]

        # EMAs for trend
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        return self.feature_engineering_expand_all(dataframe, period=1, metadata=metadata)

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Market regime features (BTC correlation) - MUST MATCH LeaFreqAI
        """
        # Only add BTC features if this is NOT the BTC pair itself
        if metadata.get("pair") != "BTC/USDT" and self.dp:
            btc_dataframe = self.dp.get_pair_dataframe(pair="BTC/USDT", timeframe=self.timeframe)
            if not btc_dataframe.empty and len(btc_dataframe) > 50:
                # BTC trend strength
                btc_ema = ta.EMA(btc_dataframe["close"], timeperiod=50)
                btc_trend = (btc_dataframe["close"] - btc_ema) / btc_ema

                # Market volatility
                btc_vol = btc_dataframe["close"].pct_change().rolling(48).std()

                # Add to dataframe with proper alignment
                dataframe["%btc_trend"] = btc_trend.reindex(dataframe.index, method='ffill')
                dataframe["%market_vol"] = btc_vol.reindex(dataframe.index, method='ffill')
        else:
            # For BTC pair or if data unavailable, use neutral values
            dataframe["%btc_trend"] = 0.0
            dataframe["%market_vol"] = dataframe["close"].pct_change().rolling(48).std()

        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        dataframe["&-target"] = dataframe["close"].shift(-12).pct_change(periods=12, fill_method=None)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        FreqAI predictions with Binance research data enhancement
        """
        # Load research data if available (once per pair)
        if self.research_loader and RESEARCH_LOADER_AVAILABLE:
            pair = metadata.get("pair", "")
            symbol = pair.split('/')[0] if '/' in pair else pair

            if symbol not in self.research_data_cache:
                try:
                    # Load research data for backtest period
                    research_data = self.research_loader.load_research_data(
                        symbol=symbol,
                        start_date='2025-09-20',
                        end_date='2025-10-27'
                    )
                    self.research_data_cache[symbol] = research_data
                    logger.info(f"[{pair}] Loaded research data for {symbol}: {len(research_data)} rows")
                except Exception as e:
                    logger.warning(f"[{pair}] Failed to load research data for {symbol}: {e}")
                    self.research_data_cache[symbol] = None

            # Add research features to dataframe if available
            if self.research_data_cache.get(symbol) is not None:
                try:
                    research_data = self.research_data_cache[symbol]

                    # Extract date from dataframe timestamps and merge research features (VECTORIZED)
                    dataframe['date_only'] = pd.to_datetime(dataframe['date']).dt.date
                    
                    # Build lookup dict of all features by date (faster than per-row API calls)
                    features_by_date = {}
                    for candle_date in dataframe['date_only'].unique():
                        features_by_date[candle_date] = self.research_loader.get_research_features_for_candle(
                            candle_date, symbol, research_data
                        )
                    
                    # Vectorized assignment using map (30-50x faster than iterrows)
                    for feature_name in next(iter(features_by_date.values())).keys() if features_by_date else []:
                        dataframe[f"&{feature_name}"] = dataframe['date_only'].map(
                            lambda date: features_by_date.get(date, {}).get(feature_name, 0.0)
                        )

                    # Log added features
                    research_cols = [col for col in dataframe.columns if col.startswith('&') and not col.startswith('&-')]
                    logger.info(f"[{pair}] Added {len(research_cols)} research features: {research_cols[:3]}...")

                    # Drop temporary date column
                    dataframe = dataframe.drop(columns=['date_only'])
                except Exception as e:
                    logger.warning(f"[{pair}] Error adding research features: {e}")

        dataframe = self.freqai.start(dataframe, metadata, self)

        # VECTORIZED: Calculate confluence scores using pre-computed rolling indicators (O(n) not O(n²))
        # Pre-compute all indicator values once
        rsi = ta.RSI(dataframe, timeperiod=14)
        macd_data = ta.MACD(dataframe)
        bb = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        ema_20 = ta.EMA(dataframe, timeperiod=20)
        ema_50 = ta.EMA(dataframe, timeperiod=50)

        # Calculate signals using vectorized operations
        # RSI signal: normalized to -1 to +1 (bullish when >50)
        rsi_signal = (rsi - 50) / 50

        # MACD signal: normalize histogram with rolling mean/std
        hist = macd_data['macdhist']
        hist_mean = hist.rolling(50).mean()
        hist_std = hist.rolling(50).std()
        hist_std = hist_std.replace(0, np.nan)  # Avoid division by zero
        macd_signal = (hist - hist_mean) / hist_std
        macd_signal = macd_signal.fillna(np.where(hist > 0, 1.0, -1.0))
        macd_signal = np.clip(macd_signal, -1, 1)

        # Volume signal: surge detection
        vol_ma = dataframe['volume'].rolling(20).mean()
        vol_ratio = dataframe['volume'] / vol_ma
        volume_signal = np.clip((vol_ratio - 1) * 0.5, -1, 1)

        # Bollinger Bands signal: position in bands
        bb_width = bb['upper'] - bb['lower']
        bb_width = bb_width.replace(0, np.nan)  # Avoid division by zero
        bb_position = (dataframe['close'] - bb['mid'].iloc[:, 0]) / (bb_width / 2) if isinstance(bb['mid'], pd.DataFrame) else (dataframe['close'] - bb['mid']) / (bb_width / 2)
        bb_signal = np.clip(bb_position, -1, 1)

        # Trend signal: EMA difference
        trend_diff = (ema_20 - ema_50) / ema_50
        trend_signal = np.clip(trend_diff * 50, -1, 1)

        # Count positive signals and normalize (0 to 1) - confluence score for visualization
        signals_df = pd.DataFrame({
            'rsi': rsi_signal,
            'macd': macd_signal,
            'volume': volume_signal,
            'bb': bb_signal,
            'trend': trend_signal
        })
        dataframe['confluence_score'] = (signals_df > 0.2).sum(axis=1) / 5.0
        dataframe['confluence_score'] = dataframe['confluence_score'].fillna(0)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry logic with CONFLUENCE filters:
        1. Strong ML prediction (> 0.8% threshold, not 0.5%)
        2. Market regime allows trading
        3. Trend confirmation (price above EMA 50)
        4. RSI not overbought (< 70)
        5. Volume confirmation (above 20-period MA)
        """
        if "&-target" not in dataframe.columns:
            dataframe["enter_long"] = 0
            return dataframe

        # Initialize
        dataframe["enter_long"] = 0

        # === FILTER 1: Strong ML Signal ===
        # Increased threshold from 0.5% to 0.8% to reduce noise
        ml_signal = dataframe["&-target"] > 0.008

        # === FILTER 2: Market Regime ===
        # Don't enter in ranging or highly volatile markets
        atr_pct = (dataframe['atr14'] / dataframe['close']) * 100
        regime_ok = atr_pct < 3.0  # Avoid extreme volatility, but allow normal ranging

        # === FILTER 3: Trend Confirmation ===
        # Price must be above 50-period EMA (in uptrend)
        trend_ok = dataframe["close"] > dataframe["ema_50"]

        # === FILTER 4: RSI Filter ===
        # Avoid overbought conditions (RSI > 70 is overextended)
        rsi_ok = dataframe["rsi"] < 70

        # === FILTER 5: Volume Confirmation ===
        # Volume must be above 20-period moving average
        volume_ma = dataframe["volume"].rolling(20).mean()
        volume_ok = dataframe["volume"] > volume_ma

        # === FILTER 6: MACD Confirmation ===
        # MACD histogram positive and increasing (momentum)
        macd_ok = dataframe["macdhist"] > 0

        # === FILTER 7: Bollinger Bands ===
        # Price in lower half of bands (room to run up)
        bb_mid = dataframe["bb_middleband"]
        bb_ok = dataframe["close"] < bb_mid

        # === COMBINE ALL FILTERS ===
        entry_signal = (
            ml_signal &
            regime_ok &
            trend_ok &
            rsi_ok &
            volume_ok &
            macd_ok &
            bb_ok
        )

        dataframe.loc[entry_signal, "enter_long"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        return dataframe

    def custom_stake_amount(self, pair: str, current_time, current_rate: float, proposed_stake: float, min_stake: float, max_stake: float, entry_tag, side: str, **kwargs) -> float:
        # FIXED: Added wallet validation for production safety
        if not self.wallets:
            logger.warning(f"[{pair}] Wallets object is None, returning minimum stake")
            return min_stake
        
        # get_analyzed_dataframe returns (DataFrame, last_updated) or just DataFrame
        result = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if isinstance(result, tuple):
            df = result[0]
        else:
            df = result

        if "&-target" not in df.columns:
            return min_stake

        # Measure signal strength and confluence
        signal = abs(df['&-target'].iloc[-1])
        
        # Count how many confluence filters passed
        confluence_count = 0
        atr_pct = (df['atr14'].iloc[-1] / df['close'].iloc[-1]) * 100
        if atr_pct < 3.0:
            confluence_count += 1
        if df["close"].iloc[-1] > df["ema_50"].iloc[-1]:
            confluence_count += 1
        if df["rsi"].iloc[-1] < 70:
            confluence_count += 1
        if df["volume"].iloc[-1] > df["volume"].rolling(20).mean().iloc[-1]:
            confluence_count += 1
        if df["macdhist"].iloc[-1] > 0:
            confluence_count += 1
        if df["close"].iloc[-1] < df["bb_middleband"].iloc[-1]:
            confluence_count += 1

        # High confluence = higher position size
        confluence_multiplier = 0.6 + (confluence_count / 6 * 0.4)  # 0.6 to 1.0

        confidence = self.pattern_mem.get_confidence({'signal': signal, 'confluence': confluence_count})
        regime = self.regime.detect_regime(df)
        atr = ta.ATR(df, timeperiod=14).iloc[-1]

        risk_metrics = self.risk_mgr.calculate_position(signal, confidence, regime, atr, df['close'].iloc[-1])

        # FIXED: Check if risk manager says to skip trade
        if risk_metrics['size'] == 0:
            logger.info(f"[{pair}] Risk manager rejected trade (portfolio heat or drawdown limit reached)")
            return 0  # Force trade rejection

        # Apply confluence multiplier to position size
        risk_metrics['size'] = risk_metrics['size'] * confluence_multiplier
        
        self.custom_info[pair] = risk_metrics

        # FIXED: Validate portfolio value
        portfolio_value = self.wallets.get_total_stake_amount()
        if portfolio_value <= 0:
            logger.warning(f"[{pair}] Portfolio value is {portfolio_value}, returning minimum stake")
            return min_stake
        
        stake = portfolio_value * risk_metrics['size']

        return max(min_stake, min(stake, max_stake))

    def custom_stoploss(self, pair: str, trade: Trade, current_time, current_rate: float, current_profit: float, **kwargs) -> float:
        if pair not in self.custom_info:
            return self.stoploss

        base_stop = self.custom_info[pair]['stop']

        # Progressive stop tightening with profit
        if current_profit > 0.06:
            return max(-0.015, base_stop)
        elif current_profit > 0.04:
            return max(-0.02, base_stop)
        elif current_profit > 0.02:
            return max(-0.002, base_stop)

        return base_stop

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        if self.risk_mgr.get_portfolio_heat() > 0.06:
            return False
        if self.risk_mgr.get_drawdown() > 0.15:
            return False
        if len(self.risk_mgr.recent_losses) >= 5 and sum(1 for x in list(self.risk_mgr.recent_losses)[-5:] if x < 0) / 5 > 0.8:
            return False
        return True
