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

    # ROI table - More achievable profit targets
    minimal_roi = {
        "0": 0.015,   # 1.5% immediate profit (was 2%)
        "30": 0.01,   # 1% after 30 min (was 1.5% at 20 min)
        "60": 0.008,  # 0.8% after 1 hour (was 1% at 40 min)
        "120": 0.005  # 0.5% after 2 hours (was 1.5 hours)
    }

    # Stoploss - Fixed stoploss (optimal balance found through testing)
    stoploss = -0.05  # 5% hard stop
    use_custom_stoploss = False  # Disabled - simple fixed stoploss performs best

    # Trailing stop - Enabled to protect profits
    trailing_stop = True
    trailing_stop_positive = 0.005  # Activate trailing at +0.5% profit
    trailing_stop_positive_offset = 0.01  # Trail 1% below peak (locks in profit above +1%)

    # Exit settings - Disable exit signals, use ROI/stoploss/trailing only
    use_exit_signal = False  # Our ROI exits perform much better than signal exits
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
                    "&-target": {"color": "green"},
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
        NOTE: Predictions are returned in the TARGET column (&-target), not &-prediction!
        """
        # FreqAI will add predictions to the target column
        dataframe = self.freqai.start(dataframe, metadata, self)

        # Calculate RSI and other indicators needed for entry/exit logic
        # (FreqAI doesn't preserve all features from feature_engineering)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        # DEBUG: Check if predictions were added
        if "&-target" in dataframe.columns:
            pred_col = dataframe["&-target"]
            logger.info(f"[{metadata['pair']}] Predictions added to &-target: {len(pred_col)} rows")
            logger.info(f"[{metadata['pair']}] Prediction stats: min={pred_col.min():.6f}, max={pred_col.max():.6f}, mean={pred_col.mean():.6f}")
            logger.info(f"[{metadata['pair']}] Predictions > 0: {(pred_col > 0).sum()} ({(pred_col > 0).sum() / len(pred_col) * 100:.1f}%)")
        else:
            logger.warning(f"[{metadata['pair']}] WARNING: &-target column NOT found after freqai.start()!")
            logger.warning(f"[{metadata['pair']}] Available columns: {dataframe.columns.tolist()}")

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry signals - IMPROVED VERSION with filters
        NOTE: Predictions are in &-target column, not &-prediction!
        """
        # Check if predictions are available
        if "&-target" not in dataframe.columns:
            logger.warning(f"[{metadata['pair']}] No &-target column in populate_entry_trend!")
            dataframe["enter_long"] = 0
            return dataframe

        conditions = []

        # ML prediction must be positive (increased to 0.5% for better selectivity)
        conditions.append(dataframe["&-target"] > 0.005)

        # DI filter must have passed (model confident in prediction)
        if "do_predict" in dataframe.columns:
            conditions.append(dataframe["do_predict"] == 1)

        # Trend filter: price above 50 EMA (uptrend) - KEEP THIS, it's important
        conditions.append(dataframe["close"] > dataframe["ema_50"])

        # RSI filter: avoid overbought conditions (re-enabled to prevent buying at tops)
        conditions.append(dataframe["rsi"] < 70)

        # Volume filter: slightly above average (reduced from 24h to 20h rolling mean)
        conditions.append(dataframe["volume"] > dataframe["volume"].rolling(20).mean())

        # Combine all conditions
        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                "enter_long"
            ] = 1

        # DEBUG: Log entry signals
        entry_count = dataframe["enter_long"].sum()
        logger.info(f"[{metadata['pair']}] Entry signals generated: {entry_count}")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit signals based on ML predictions - IMPROVED
        NOTE: Predictions are in &-target column, not &-prediction!
        """
        # Check if predictions are available
        if "&-target" not in dataframe.columns:
            dataframe["exit_long"] = 0
            return dataframe

        # ONLY exit on strong negative ML prediction
        # Let ROI and stoploss handle everything else
        dataframe.loc[
            dataframe["&-target"] < -0.004,  # Only exit on -0.4% predicted loss or worse
            "exit_long"
        ] = 1

        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        """
        Final trade confirmation before entry - IMPROVED
        NOTE: Predictions are in &-target column, not &-prediction!
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]

        # Check if predictions are available
        if "&-target" not in dataframe.columns:
            return False

        # Require positive prediction (at least 0.5%)
        if last_candle["&-target"] <= 0.005:
            return False

        # Confirm DI filter passed
        if "do_predict" in dataframe.columns:
            if last_candle["do_predict"] != 1:
                return False

        # Confirm uptrend
        if last_candle["close"] <= last_candle["ema_50"]:
            return False

        return True

    def custom_stake_amount(self, pair: str, current_time, current_rate: float,
                           proposed_stake: float, min_stake: float, max_stake: float,
                           entry_tag, side: str, **kwargs) -> float:
        """
        Dynamic position sizing based on prediction confidence
        NOTE: Predictions are in &-target column, not &-prediction!
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]

        # Check if predictions are available
        if "&-target" not in dataframe.columns:
            return proposed_stake

        # Get prediction confidence
        prediction = last_candle["&-target"]

        # Scale stake by prediction magnitude (0.5x to 1.5x)
        confidence_multiplier = np.clip(1.0 + (prediction * 10), 0.5, 1.5)

        adjusted_stake = proposed_stake * confidence_multiplier

        # Ensure within limits
        return np.clip(adjusted_stake, min_stake, max_stake)
