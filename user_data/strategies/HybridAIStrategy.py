"""
Hybrid AI Strategy - Combining LEA FreqAI + Traditional Technical Indicators
Combines ML predictions with proven technical analysis for robust trading signals
"""
import logging
from functools import reduce
import numpy as np
import pandas as pd
from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib

from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)


class HybridAIStrategy(IStrategy):
    """
    Hybrid strategy combining:
    - LEA FreqAI ML predictions (forward-looking)
    - Traditional technical indicators (current state)
    - Market regime detection (BTC correlation)
    """

    # Strategy metadata
    INTERFACE_VERSION = 3
    can_short = False

    # Timeframe
    timeframe = "5m"

    # Startup candles needed for indicators
    startup_candle_count = 200

    # ROI table - balanced approach
    minimal_roi = {
        "0": 0.08,   # 8% if immediate
        "20": 0.05,  # 5% after 20 min
        "40": 0.03,  # 3% after 40 min
        "60": 0.01   # 1% after 1 hour
    }

    # Stoploss
    stoploss = -0.10  # 10% hard stop (tighter than LEA)

    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.015
    trailing_only_offset_is_reached = True

    # Exit settings
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Process only new candles
    process_only_new_candles = True

    # Order types
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False
    }

    order_time_in_force = {
        "entry": "GTC",
        "exit": "GTC"
    }

    # Plot configuration
    @property
    def plot_config(self):
        return {
            "main_plot": {
                "ema_50": {"color": "blue"},
                "ema_200": {"color": "orange"},
            },
            "subplots": {
                "RSI": {
                    "rsi": {"color": "red"},
                },
                "MACD": {
                    "macd": {"color": "blue"},
                    "macdsignal": {"color": "orange"},
                },
                "AI Predictions": {
                    "&-target": {"color": "green"},
                }
            }
        }

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int,
                                       metadata: dict, **kwargs) -> DataFrame:
        """
        Create stationary features for FreqAI (from LEA)
        """
        # Price returns (stationary)
        dataframe[f"%ret_1"] = dataframe["close"].pct_change(1)
        dataframe[f"%ret_3"] = dataframe["close"].pct_change(3)
        dataframe[f"%ret_12"] = dataframe["close"].pct_change(12)

        # Volatility (ATR-based, relative)
        dataframe["atr14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe[f"%atr14_rel"] = dataframe["atr14"] / dataframe["close"]

        # Range (stationary)
        dataframe[f"%rng_24"] = (dataframe["high"].rolling(24).max() -
                                  dataframe["low"].rolling(24).min()) / dataframe["close"]

        # Z-score (mean reversion indicator)
        returns = dataframe["close"].pct_change()
        dataframe[f"%z_48"] = (returns - returns.rolling(48).mean()) / returns.rolling(48).std()

        # Volume indicators
        dataframe[f"%vol_z_48"] = ((dataframe["volume"] - dataframe["volume"].rolling(48).mean()) /
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
        """
        Basic feature engineering for main timeframe
        """
        dataframe = self.feature_engineering_expand_all(dataframe, period=1, metadata=metadata)
        return dataframe

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Market regime features (BTC correlation)
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
        """
        Define the prediction target
        Target: Future return over next 12 candles (1 hour at 5m)
        """
        dataframe["&-target"] = dataframe["close"].shift(-12).pct_change(periods=12, fill_method=None)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        FreqAI will populate predictions here
        """
        # FreqAI will add the prediction column
        dataframe = self.freqai.start(dataframe, metadata, self)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        HYBRID Entry: ML predictions + Traditional indicators

        Strategy: Both must agree for entry
        - AI: Positive prediction (lower threshold than LEA)
        - Technical: EMA trend + RSI + MACD confirmation
        """
        # Check if predictions are available
        if "&-target" not in dataframe.columns:
            dataframe["enter_long"] = 0
            return dataframe

        conditions = []

        # === AI COMPONENT (from LEA, relaxed) ===
        # Lower threshold: 0.1% instead of 0.5%
        conditions.append(dataframe["&-target"] > 0.001)

        # === TECHNICAL COMPONENT (from EnhancedTrend) ===
        # Trend: Price above EMA 50 (not 200, more dynamic)
        # Find EMA 50 column dynamically (FreqAI creates columns like ema_50_gen_PAIR_5m)
        ema50_cols = [col for col in dataframe.columns if 'ema_50' in col.lower() and '_gen_' in col]
        if ema50_cols:
            conditions.append(dataframe["close"] > dataframe[ema50_cols[0]])

        # Trend: EMA 50 above EMA 200 (uptrend)
        ema200_cols = [col for col in dataframe.columns if 'ema_200' in col.lower() and '_gen_' in col]
        if ema50_cols and ema200_cols:
            conditions.append(dataframe[ema50_cols[0]] > dataframe[ema200_cols[0]])

        # Momentum: RSI not overbought
        # Find RSI column dynamically
        rsi_cols = [col for col in dataframe.columns if 'rsi' in col.lower() and '_gen_' in col]
        if rsi_cols:
            conditions.append(dataframe[rsi_cols[0]] < 70)

        # Momentum: MACD bullish
        # Find MACD columns dynamically
        macd_cols = [col for col in dataframe.columns if col.startswith('macd') and '_gen_' in col]
        macdsig_cols = [col for col in dataframe.columns if col.startswith('macdsignal') and '_gen_' in col]
        if macd_cols and macdsig_cols:
            conditions.append(dataframe[macd_cols[0]] > dataframe[macdsig_cols[0]])

        # === MARKET REGIME FILTER (from LEA) ===
        # BTC not crashing (if available)
        if "%btc_trend" in dataframe.columns:
            conditions.append(dataframe["%btc_trend"] > -0.05)  # Relaxed from -0.10

        # === VOLUME FILTER ===
        conditions.append(dataframe["volume"] > 0)

        # Combine all conditions
        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                "enter_long"
            ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        HYBRID Exit: ML predictions OR Traditional signals

        Exit if EITHER condition is met:
        - AI: Negative prediction
        - Technical: MACD bearish OR RSI overbought
        """
        # Check if predictions are available
        if "&-target" not in dataframe.columns:
            dataframe["exit_long"] = 0
            return dataframe

        conditions = []

        # === AI EXIT ===
        # Negative prediction
        ai_exit = dataframe["&-target"] < -0.001

        # === TECHNICAL EXIT ===
        # MACD bearish - find columns dynamically
        macd_cols = [col for col in dataframe.columns if col.startswith('macd') and '_gen_' in col and not col.startswith('macdsignal')]
        macdsig_cols = [col for col in dataframe.columns if col.startswith('macdsignal') and '_gen_' in col]
        if macd_cols and macdsig_cols:
            macd_exit = dataframe[macd_cols[0]] < dataframe[macdsig_cols[0]]
        else:
            macd_exit = False

        # RSI extreme overbought - find column dynamically
        rsi_cols = [col for col in dataframe.columns if 'rsi' in col.lower() and '_gen_' in col]
        if rsi_cols:
            rsi_exit = dataframe[rsi_cols[0]] > 80
        else:
            rsi_exit = False

        # Combine with OR logic (exit if any condition)
        dataframe.loc[
            ai_exit | macd_exit | rsi_exit,
            "exit_long"
        ] = 1

        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        """
        Final trade confirmation - relaxed from LEA
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]

        # Check if predictions are available
        if "&-target" not in dataframe.columns:
            return False

        # Lower threshold: 0.05% predicted return (was 0.5% in LEA)
        if last_candle["&-target"] < 0.0005:
            return False

        # Check volume is reasonable (relaxed from 50% to 30%)
        avg_volume = dataframe["volume"].rolling(20).mean().iloc[-1]
        if last_candle["volume"] < avg_volume * 0.3:
            return False

        return True

    def custom_stake_amount(self, pair: str, current_time, current_rate: float,
                           proposed_stake: float, min_stake: float, max_stake: float,
                           entry_tag, side: str, **kwargs) -> float:
        """
        Dynamic position sizing based on prediction confidence
        More conservative than LEA
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]

        # Check if predictions are available
        if "&-prediction" not in dataframe.columns:
            return proposed_stake

        # Get prediction confidence
        prediction = last_candle["&-prediction"]

        # Scale stake by prediction magnitude (0.7x to 1.3x) - more conservative
        confidence_multiplier = np.clip(1.0 + (prediction * 5), 0.7, 1.3)

        adjusted_stake = proposed_stake * confidence_multiplier

        # Ensure within limits
        return np.clip(adjusted_stake, min_stake, max_stake)
