"""
Diagnostic Strategy - Minimal filters to identify blocking conditions
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


class DiagnosticStrategy(IStrategy):
    """
    Ultra-minimal strategy to diagnose what's blocking trades
    """

    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "5m"
    startup_candle_count = 200

    # Very aggressive ROI
    minimal_roi = {
        "0": 0.05,   # 5%
        "30": 0.02,  # 2%
        "60": 0.01   # 1%
    }

    stoploss = -0.10
    trailing_stop = False
    use_exit_signal = True
    exit_profit_only = False
    process_only_new_candles = True

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

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int,
                                       metadata: dict, **kwargs) -> DataFrame:
        # Minimal features
        dataframe[f"%ret_1"] = dataframe["close"].pct_change(1)
        dataframe[f"%ret_12"] = dataframe["close"].pct_change(12)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        dataframe = self.feature_engineering_expand_all(dataframe, period=1, metadata=metadata)
        return dataframe

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        # No BTC filters
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        dataframe["&-target"] = dataframe["close"].shift(-12).pct_change(periods=12, fill_method=None)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.freqai.start(dataframe, metadata, self)

        # Add diagnostic columns
        if "&-target" in dataframe.columns:
            dataframe["pred_positive"] = (dataframe["&-target"] > 0.0).astype(int)
            dataframe["pred_strong"] = (dataframe["&-target"] > 0.001).astype(int)
            dataframe["rsi_ok"] = (dataframe["rsi"] < 70).astype(int)
            dataframe["price_above_ema"] = (dataframe["close"] > dataframe["ema_50"]).astype(int)

            # Log diagnostics
            total_candles = len(dataframe)
            pred_positive_count = dataframe["pred_positive"].sum()
            pred_strong_count = dataframe["pred_strong"].sum()
            rsi_ok_count = dataframe["rsi_ok"].sum()
            price_above_ema_count = dataframe["price_above_ema"].sum()

            logger.info(f"=== DIAGNOSTICS for {metadata.get('pair', 'UNKNOWN')} ===")
            logger.info(f"Total candles: {total_candles}")
            logger.info(f"Predictions > 0.0: {pred_positive_count} ({100*pred_positive_count/total_candles:.1f}%)")
            logger.info(f"Predictions > 0.001: {pred_strong_count} ({100*pred_strong_count/total_candles:.1f}%)")
            logger.info(f"RSI < 70: {rsi_ok_count} ({100*rsi_ok_count/total_candles:.1f}%)")
            logger.info(f"Price > EMA50: {price_above_ema_count} ({100*price_above_ema_count/total_candles:.1f}%)")

            # Check prediction range
            pred_min = dataframe["&-target"].min()
            pred_max = dataframe["&-target"].max()
            pred_mean = dataframe["&-target"].mean()
            logger.info(f"Prediction range: {pred_min:.6f} to {pred_max:.6f}, mean: {pred_mean:.6f}")

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        MINIMAL ENTRY: Just positive AI prediction
        Fixed: Changed &-prediction to &-target (correct column name)
        """
        if "&-target" not in dataframe.columns:
            dataframe["enter_long"] = 0
            return dataframe

        # ONLY ONE CONDITION: Positive prediction
        dataframe.loc[
            dataframe["&-target"] > 0.0,  # Any positive prediction
            "enter_long"
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        MINIMAL EXIT: Negative prediction
        Fixed: Changed &-prediction to &-target (correct column name)
        """
        if "&-target" not in dataframe.columns:
            dataframe["exit_long"] = 0
            return dataframe

        dataframe.loc[
            dataframe["&-target"] < 0.0,
            "exit_long"
        ] = 1

        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        """
        NO CONFIRMATION - Allow all trades
        """
        return True
