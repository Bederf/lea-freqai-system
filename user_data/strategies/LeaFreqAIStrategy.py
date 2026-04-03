"""
LEA FreqAI Strategy - Integrated Version
LSTM Ensemble Algorithmic Trading Strategy

Integrated features:
- Pivot-based entry filtering (bullish bias, resistance avoidance)
- Quantile-filtered ML entries (top 20% predictions only)
- ATR-based dynamic stop-loss (tightens with profit)
- Time-horizon exits (60 minutes max hold)
- Pivot take-profit (R1) + partial TP signal
- Exit priority: time > pivot TP > partial TP > hard stop

Based on: Deep Learning in Quantitative Trading (Zhang & Zohren, 2025)
"""
import logging
from datetime import timedelta
from functools import reduce
import numpy as np
import pandas as pd
from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib

from freqtrade.strategy import IStrategy, Trade

# Import research data loader for backtest/hyperopt enhancement
try:
    from binance_research_backtest_loader import BinanceBacktestResearchLoader
    RESEARCH_LOADER_AVAILABLE = True
except ImportError:
    RESEARCH_LOADER_AVAILABLE = False
    logger_init = logging.getLogger(__name__)
    logger_init.warning("Research loader not available - running without Binance research data")

logger = logging.getLogger(__name__)


def _apply_freqai_fallback(dataframe: DataFrame) -> DataFrame:
    """
    Keep the strategy loop alive when FreqAI cannot build a valid live frame.
    The fallback is intentionally fail-closed so entries are skipped until
    valid predictions return.
    """
    dataframe["&-target"] = 0.0
    dataframe["do_predict"] = 0
    return dataframe


def _get_latest_signal_candle(dataframe: DataFrame) -> pd.Series:
    """
    FreqAI frequently leaves the newest in-progress candle with a zero target and
    do_predict=0. Confirm entries against the latest completed candle instead.
    """
    if len(dataframe) == 0:
        return pd.Series(dtype=float)
    if len(dataframe) == 1:
        return dataframe.iloc[-1]
    return dataframe.iloc[-2]


class LeaFreqAIStrategy(IStrategy):
    """
    LEA Base Strategy with FreqAI LSTM predictions

    Integrated:
    - Pivot-based entry filters (close between pivot and R1)
    - Quantile-filtered ML (top 20% predictions only)
    - ATR-based dynamic stop-loss
    - 60-minute time horizon exit
    - Pivot R1 take-profit + partial TP signal
    """

    # Strategy metadata
    INTERFACE_VERSION = 3
    can_short = False

    # Timeframe
    timeframe = "5m"

    # Startup candles needed for indicators
    startup_candle_count = 200

    # =====================================================================
    # ML THRESHOLDS & QUANTILES
    # =====================================================================
    ml_entry_threshold = 0.01
    ml_quantile_threshold = 0.80  # Top 20% of predictions only

    # =====================================================================
    # ATR STOP-LOSS
    # =====================================================================
    atr_period = 14
    atr_multiplier = 1.5  # Stop distance = ATR × multiplier

    # =====================================================================
    # TIME & EXIT
    # =====================================================================
    max_hold_minutes = 60
    partial_tp_enabled = True
    partial_tp_profit = 0.01  # Exit signal at 1% profit
    hard_stop = -0.03

    # =====================================================================
    # ROI & STOPLOSS
    # =====================================================================
    # Partial TP: first tier takes ~50% at 1%, second tier runs until pivot/time
    minimal_roi = {
        "0": 0.015,   # Immediate profit - aggressive entry
        "30": 0.010,  # 1% after 30 min
        "60": 0.008,  # 0.8% after 1 hour
        "120": 0.005, # 0.5% after 2 hours
    }

    stoploss = -0.20
    trailing_stop = False
    use_custom_stoploss = True  # Enable for ATR-based dynamic stop

    # Exit settings
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Process only new candles
    process_only_new_candles = True

    # Optimal order types
    order_types = {
        "entry": "market",
        "exit": "market",
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

    def __init__(self, config: dict) -> None:
        """
        Initialize strategy with research loader
        """
        super().__init__(config)
        self.enable_live_research_features = False
        self._atr_cache: dict[str, float] = {}

        # Initialize research data loader
        self.research_loader = None
        self.research_data_cache = {}  # Cache loaded research data by symbol

        if RESEARCH_LOADER_AVAILABLE:
            try:
                self.research_loader = BinanceBacktestResearchLoader()
                logger.info("Research loader initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize research loader: {e}")

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
        FreqAI predictions with indicators + pivot points + quantile
        """
        # FreqAI will add predictions to the target column
        try:
            dataframe = self.freqai.start(dataframe, metadata, self)
        except Exception as exc:
            pair = metadata.get("pair", "UNKNOWN")
            logger.warning(
                f"[{pair}] FreqAI prediction failed ({exc.__class__.__name__}: {exc}). "
                "Using fail-closed fallback frame."
            )
            dataframe = _apply_freqai_fallback(dataframe)

        # Calculate RSI and other indicators needed for entry/exit logic
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # Volume
        dataframe["vol_mean_20"] = dataframe["volume"].rolling(20).mean()

        # === ATR (for dynamic stop-loss) ===
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=self.atr_period)

        # === Prediction quantile (top X% only) ===
        if "&-target" in dataframe.columns:
            dataframe["pred_quantile"] = dataframe["&-target"].rank(pct=True)

        # === Pivot Points (previous candle — no lookahead) ===
        dataframe["pivot"] = (
            dataframe["high"].shift(1)
            + dataframe["low"].shift(1)
            + dataframe["close"].shift(1)
        ) / 3

        dataframe["r1"] = (2 * dataframe["pivot"]) - dataframe["low"].shift(1)
        dataframe["s1"] = (2 * dataframe["pivot"]) - dataframe["high"].shift(1)

        dataframe["r2"] = dataframe["pivot"] + (
            dataframe["high"].shift(1) - dataframe["low"].shift(1)
        )
        dataframe["s2"] = dataframe["pivot"] - (
            dataframe["high"].shift(1) - dataframe["low"].shift(1)
        )

        # DEBUG: Check predictions
        if "&-target" in dataframe.columns:
            pred_col = dataframe["&-target"]
            logger.debug(
                f"[{metadata['pair']}] Predictions: min={pred_col.min():.6f}, "
                f"max={pred_col.max():.6f}, mean={pred_col.mean():.6f}"
            )

        return dataframe

    def _quantile_filter(self, dataframe: DataFrame, pred_col: str) -> pd.Series:
        """Return mask for top X% predictions (ml_quantile_threshold)."""
        if "pred_quantile" in dataframe.columns:
            return dataframe["pred_quantile"] >= self.ml_quantile_threshold
        return dataframe[pred_col] >= dataframe[pred_col].quantile(self.ml_quantile_threshold)

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry signals with pivot + quantile filters.

        LEA entry requirements:
        1. ML prediction > threshold AND in top quantile
        2. do_predict == 1 (model confidence)
        3. close > pivot (bullish bias)
        4. close < r1 (avoid resistance)
        5. RSI < 70 (not overbought)
        6. Volume > 0
        """
        if "&-target" not in dataframe.columns:
            logger.warning(f"[{metadata['pair']}] No &-target column in populate_entry_trend!")
            dataframe["enter_long"] = 0
            return dataframe

        pred_col = "&-target"

        conditions = [
            dataframe[pred_col] > self.ml_entry_threshold,
            self._quantile_filter(dataframe, pred_col),
            dataframe["do_predict"] == 1 if "do_predict" in dataframe.columns else pd.Series(True, index=dataframe.index),
            dataframe["close"] > dataframe["pivot"],      # Bullish bias
            dataframe["close"] < dataframe["r1"],          # Avoid resistance (between pivot and R1)
            dataframe["rsi"] < 70,
            dataframe["volume"] > 0,
        ]

        entry_signal = reduce(lambda x, y: x & y, conditions)
        dataframe["enter_long"] = 0
        dataframe.loc[entry_signal, "enter_long"] = 1

        entry_count = dataframe["enter_long"].sum()
        logger.debug(f"[{metadata['pair']}] LEA entry signals: {entry_count}/{len(dataframe)}")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Keep exit trend neutral. All exits handled by custom_exit() and custom_stoploss().
        """
        dataframe["exit_long"] = 0
        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        """
        ATR-based dynamic stop-loss.
        Stop distance = entry_price - (ATR × atr_multiplier)
        Tightens as profit increases.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return self.stoploss

        last = dataframe.iloc[-1]
        atr = last.get("atr")

        if atr is None or pd.isna(atr):
            return self.stoploss

        self._atr_cache[pair] = float(atr)

        entry_price = trade.open_rate
        stop_distance = self.atr_multiplier * atr
        stop_price = entry_price - stop_distance
        stop_pct = (stop_price / entry_price) - 1

        # Progressive stop tightening with profit
        if current_profit > 0.030:
            stop_price = max(entry_price * 0.995, stop_price)
            stop_pct = (stop_price / entry_price) - 1
        elif current_profit > 0.015:
            stop_price = max(entry_price * 0.998, stop_price)
            stop_pct = (stop_price / entry_price) - 1
        elif current_profit > 0.008:
            half_dist = stop_distance * 0.5
            stop_price = entry_price - half_dist
            stop_pct = (stop_price / entry_price) - 1

        return max(stop_pct, -abs(self.stoploss))

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | bool | None:
        """
        LEA exit logic — priority order:
        1. Time exit (60 min) — no conditions, fires first
        2. Pivot R1 take-profit
        3. Partial TP signal at 1% profit
        4. Hard stop at -3%
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None

        last = dataframe.iloc[-1]
        trade_age = current_time - trade.open_date_utc

        # 1. HARD TIME EXIT — fires first, no conditions
        if trade_age >= timedelta(minutes=self.max_hold_minutes):
            logger.info(
                f"[{pair}] LEA exit=time_exit_horizon "
                f"age_min={trade_age.total_seconds() / 60:.1f} "
                f"profit={current_profit:.4f}"
            )
            return "time_exit_horizon"

        # 2. PIVOT R1 TAKE-PROFIT
        r1 = last.get("r1")
        if pd.notna(r1) and current_rate >= r1:
            logger.info(
                f"[{pair}] LEA exit=pivot_r1_take_profit "
                f"rate={current_rate:.8f} r1={r1:.8f} profit={current_profit:.4f}"
            )
            return "pivot_r1_take_profit"

        # 3. PARTIAL TAKE-PROFIT SIGNAL
        if self.partial_tp_enabled and current_profit >= self.partial_tp_profit:
            logger.info(
                f"[{pair}] LEA exit=partial_tp_early "
                f"profit={current_profit:.4f}"
            )
            return "partial_tp_early"

        # 4. HARD STOPLOSS GUARD
        if current_profit <= self.hard_stop:
            logger.info(
                f"[{pair}] LEA exit=hard_stoploss_guard "
                f"profit={current_profit:.4f}"
            )
            return "hard_stoploss_guard"

        return None

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time,
        entry_tag,
        side: str,
        **kwargs,
    ) -> bool:
        """
        Final confirmation: re-check pivot + quantile + trend filters.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return False

        last_candle = dataframe.iloc[-1]
        signal_candle = _get_latest_signal_candle(dataframe)

        if "&-target" not in dataframe.columns:
            return False

        target_val = float(signal_candle["&-target"])
        if target_val <= self.ml_entry_threshold:
            logger.debug(f"[{pair}] LEA confirm: pred {target_val:.6f} <= threshold {self.ml_entry_threshold}")
            return False

        quantile = signal_candle.get("pred_quantile", 0.0)
        if pd.notna(quantile) and quantile < self.ml_quantile_threshold:
            logger.debug(f"[{pair}] LEA confirm: quantile {quantile:.3f} < {self.ml_quantile_threshold}")
            return False

        close = float(signal_candle["close"])
        pivot = float(signal_candle["pivot"])
        r1 = float(signal_candle["r1"])
        if close <= pivot:
            logger.debug(f"[{pair}] LEA confirm: close {close:.8f} <= pivot {pivot:.8f}")
            return False
        if close >= r1:
            logger.debug(f"[{pair}] LEA confirm: close {close:.8f} >= r1 {r1:.8f}")
            return False

        ema50 = float(signal_candle["ema_50"])
        if close <= ema50:
            logger.debug(f"[{pair}] LEA confirm: close {close:.8f} <= ema50 {ema50:.8f}")
            return False

        rsi = float(signal_candle["rsi"])
        if rsi >= 70:
            logger.debug(f"[{pair}] LEA confirm: rsi {rsi:.1f} >= 70")
            return False

        volume = float(signal_candle["volume"])
        avg_vol = float(dataframe["volume"].rolling(20).mean().iloc[-1])
        if volume < avg_vol * 0.3:
            logger.debug(f"[{pair}] LEA confirm: volume {volume:.2f} < 30% avg {avg_vol:.2f}")
            return False

        logger.info(
            f"[{pair}] LEA entry confirmed: "
            f"pred={target_val:.6f} q={quantile:.3f} "
            f"close={close:.8f} pivot={pivot:.8f} r1={r1:.8f}"
        )
        return True

    def custom_stake_amount(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_stake: float,
        min_stake: float,
        max_stake: float,
        entry_tag,
        side: str,
        **kwargs,
    ) -> float:
        """
        Dynamic position sizing based on prediction confidence.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return proposed_stake

        signal_candle = _get_latest_signal_candle(dataframe)
        if "&-target" not in dataframe.columns:
            return proposed_stake

        prediction = float(signal_candle["&-target"])
        confidence_multiplier = np.clip(1.0 + (prediction * 10), 0.5, 1.5)
        adjusted_stake = proposed_stake * confidence_multiplier

        return np.clip(adjusted_stake, min_stake, max_stake)
