"""
LEA FreqAI Strategy - Base Implementation
LSTM Ensemble Algorithmic Trading Strategy

Based on: Deep Learning in Quantitative Trading (Zhang & Zohren, 2025)
"""
import logging
from functools import reduce
import numpy as np
import pandas as pd
from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib

from freqtrade.strategy import IStrategy, merge_informative_pair

logger = logging.getLogger(__name__)


class LeaFreqAIStrategy(IStrategy):
    """
    LEA Base Strategy with FreqAI LSTM predictions

    Features:
    - LSTM-based price prediction (via FreqAI)
    - Stationary feature engineering
    - Market regime detection
    - Risk-aware position management
    """

    # Strategy metadata
    INTERFACE_VERSION = 3
    can_short = False

    # Timeframe
    timeframe = "5m"

    # Startup candles needed for indicators
    startup_candle_count = 200

    # ROI table - dynamic based on forecast
    minimal_roi = {
        "0": 0.10,   # 10% if immediate
        "30": 0.05,  # 5% after 30 min
        "60": 0.02,  # 2% after 1 hour
        "120": 0.01  # 1% after 2 hours
    }

    # Stoploss
    stoploss = -0.15  # 15% hard stop

    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.01  # Activate at 1% profit
    trailing_stop_positive_offset = 0.02  # Trail when 2% profit
    trailing_only_offset_is_reached = True

    # Exit settings
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Process only new candles
    process_only_new_candles = True

    # Optimal order types
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
                "Predictions": {
                    "&-prediction": {"color": "green"},
                }
            }
        }

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int,
                                       metadata: dict, **kwargs) -> DataFrame:
        """
        Create stationary features for all timeframes
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
        dataframe["&-target"] = dataframe["close"].shift(-12).pct_change(12)
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
        Entry signals based on LSTM predictions + filters
        """
        # Check if predictions are available
        if "&-prediction" not in dataframe.columns:
            dataframe["enter_long"] = 0
            return dataframe

        conditions = []

        # Main signal: LSTM predicts positive return
        conditions.append(dataframe["&-prediction"] > 0.0)

        # Filter 1: Not overbought
        conditions.append(dataframe["rsi"] < 75)

        # Filter 2: Sufficient volume
        conditions.append(dataframe["volume"] > 0)

        # Filter 3: BTC not crashing (if available)
        if "%btc_trend" in dataframe.columns:
            conditions.append(dataframe["%btc_trend"] > -0.10)

        # Filter 4: Price above EMA 200 (trend filter)
        conditions.append(dataframe["close"] > dataframe["ema_200"])

        # Combine all conditions
        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                "enter_long"
            ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit signals based on LSTM predictions
        """
        # Check if predictions are available
        if "&-prediction" not in dataframe.columns:
            dataframe["exit_long"] = 0
            return dataframe

        conditions = []

        # Main signal: LSTM predicts negative return
        conditions.append(dataframe["&-prediction"] < 0.0)

        # Alternative: Extreme overbought
        conditions.append(dataframe["rsi"] > 85)

        # Combine with OR logic (exit if either condition)
        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x | y, conditions),
                "exit_long"
            ] = 1

        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        """
        Additional trade confirmation before entry
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]

        # Check if predictions are available
        if "&-prediction" not in dataframe.columns:
            return False

        # Require strong prediction confidence
        if last_candle["&-prediction"] < 0.005:  # Less than 0.5% predicted return
            return False

        # Check volume is not too low
        if last_candle["volume"] < last_candle["volume"].rolling(20).mean() * 0.5:
            return False

        return True

    def custom_stake_amount(self, pair: str, current_time, current_rate: float,
                           proposed_stake: float, min_stake: float, max_stake: float,
                           entry_tag, side: str, **kwargs) -> float:
        """
        Dynamic position sizing based on prediction confidence
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]

        # Check if predictions are available
        if "&-prediction" not in dataframe.columns:
            return proposed_stake

        # Get prediction confidence
        prediction = last_candle["&-prediction"]

        # Scale stake by prediction magnitude (0.5x to 1.5x)
        confidence_multiplier = np.clip(1.0 + (prediction * 10), 0.5, 1.5)

        adjusted_stake = proposed_stake * confidence_multiplier

        # Ensure within limits
        return np.clip(adjusted_stake, min_stake, max_stake)
