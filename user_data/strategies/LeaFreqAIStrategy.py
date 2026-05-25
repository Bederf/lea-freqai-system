"""
LEA FreqAI Strategy - Clean Configuration
Freqtrade FreqAI with XGBoostRegressor.

Exit hierarchy (active):
  1. ROI table exits  — primary exit system
  2. Hard stoploss    — -5% catastrophic loss guard

Guard mechanisms (DISABLED — do NOT re-enable):
  - ATR custom_stoploss    — burned -$0.092/trade avg, 28min avg exit
  - Time exit (custom_exit) — cut winners at market rate, -$0.123/trade avg
  - Exit signal override    — replaced ROI with uncertain market rate exits
  - Trailing stop           — -$1.36/trade avg across 242 trades

See: user_data/configs/change_log.csv for config change audit trail.
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
    ml_entry_threshold = 0.001  # 0.1% minimum prediction
    ml_quantile_threshold = 0.75  # Top 25% of predictions only

    # =====================================================================
    # ATR STOP-LOSS
    # =====================================================================
    atr_period = 14
    atr_multiplier = 1.5  # Reduced from 3.0 - tighter stop to reduce bleeding

    # =====================================================================
    # TIME & EXIT
    # =====================================================================
    max_hold_minutes = 60
    partial_tp_enabled = True
    partial_tp_profit = 0.025  # Exit signal at 2.5% profit (higher threshold)
    hard_stop = -0.03  # Hard stop at -3%
    r1_exit_on_breakdown = True  # Exit when price breaks past R1 then falls back

    # =====================================================================
    # ROI & STOPLOSS
    # =====================================================================
    minimal_roi = {
        "0": 0.02,    # 2% immediate profit
        "20": 0.015,  # 1.5% after 20 min
        "40": 0.01,   # 1% after 40 min
        "90": 0.005,  # 0.5% after 1.5 hours
    }

    stoploss = -0.015   # Tightened from -0.05 (May 24). At -5% avg loss was $1.64, expectancy -$0.15. -1.5% reduces avg loss to ~$0.45, breakeven WR drops from 89% to 72%. Current WR 81.8% is above breakeven — expectancy projected +$0.06/trade if WR holds.
    trailing_stop = False
    use_custom_stoploss = False   # Disabled: ATR stop burned avg -$0.092/trade. Hard -1.5% stoploss handles catastrophic losses.

    # Exit settings
    use_exit_signal = False    # Disabled: custom_exit was cutting winners at market rate. ROI table handles all exits.
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
        # Allow config to override max_hold_minutes
        if "max_hold_minutes" in config:
            self.max_hold_minutes = config["max_hold_minutes"]
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

        # === Supply & Demand Zones ===
        # Demand Zone: recent support (rolling min of low over 20 periods)
        dataframe["demand_zone"] = dataframe["low"].rolling(20).min()
        # Supply Zone: recent resistance (rolling max of high over 20 periods)
        dataframe["supply_zone"] = dataframe["high"].rolling(20).max()

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

        # DEBUG: Check predictions (INFO level for visibility)
        if "&-target" in dataframe.columns:
            pred_col = dataframe["&-target"]
            logger.info(
                f"[{metadata['pair']}] Predictions: min={pred_col.min():.6f}, "
                f"max={pred_col.max():.6f}, mean={pred_col.mean():.6f}, "
                f"last={pred_col.iloc[-1]:.6f}"
            )
            # Log RSI and close for debugging entry
            if "rsi" in dataframe.columns:
                logger.info(f"[{metadata['pair']}] RSI={dataframe['rsi'].iloc[-1]:.2f}, close={dataframe['close'].iloc[-1]:.6f}")
            if "pivot" in dataframe.columns and "r1" in dataframe.columns:
                logger.info(f"[{metadata['pair']}] pivot={dataframe['pivot'].iloc[-1]:.6f}, r1={dataframe['r1'].iloc[-1]:.6f}")

        return dataframe

    def _quantile_filter(self, dataframe: DataFrame, pred_col: str, threshold: float = None) -> pd.Series:
        """Return mask for top X% predictions. Default: ml_quantile_threshold."""
        if threshold is None:
            threshold = self.ml_quantile_threshold
        if "pred_quantile" in dataframe.columns:
            return dataframe["pred_quantile"] >= threshold
        return dataframe[pred_col] >= dataframe[pred_col].quantile(threshold)

    def _quantile_filter_inverted(self, dataframe: DataFrame, pred_col: str, threshold: float = None) -> pd.Series:
        """Return mask for bottom X% predictions (for inverted signal)."""
        if threshold is None:
            threshold = self.ml_quantile_threshold
        if "pred_quantile" in dataframe.columns:
            return dataframe["pred_quantile"] <= threshold
        return dataframe[pred_col] <= dataframe[pred_col].quantile(threshold)

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry signals with pivot + quantile filters (relaxed).
        """
        if "&-target" not in dataframe.columns:
            logger.warning(f"[{metadata['pair']}] No &-target column in populate_entry_trend!")
            dataframe["enter_long"] = 0
            return dataframe

        pred_col = "&-target"

        # NORMAL SIGNAL MODE: Use model predictions as-is
        # Enter LONG when prediction > 0 (model bullish = price will rise)
        # Confidence: use top quantile (above threshold)
        confidence_quantile = 0.75  # Top 25% for normal signal (high quantile = bullish)

        conditions = [
            dataframe[pred_col] > 0,  # Must be POSITIVE (model bullish → price will rise)
            dataframe[pred_col] > self.ml_entry_threshold,  # Must be significantly positive
            dataframe["do_predict"] == 1 if "do_predict" in dataframe.columns else pd.Series(True, index=dataframe.index),
            dataframe["volume"] > 0,
        ]

        # Technical filters - RSI for overbought (avoid top picking)
        if "rsi" in dataframe.columns:
            conditions.append(dataframe["rsi"] < 75)  # Not overbought

        entry_signal = reduce(lambda x, y: x & y, conditions)
        dataframe["enter_long"] = 0
        dataframe.loc[entry_signal, "enter_long"] = 1

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
        Time exit (90 min) OR ATR-based dynamic stop-loss.
        Time exit fires first: any trade open >90 min exits immediately
        at the worse of current rate or stoploss, cutting losers early.
        ATR stop only applies to profitable trades (underwater trades use time guard).
        """
        # PRIMARY EXIT: 90-minute time guard — cuts losers early
        if current_time - trade.open_date_utc >= timedelta(minutes=90):
            # Return stoploss (will trigger exit at current rate via stoploss)
            return self.stoploss

        # SECONDARY: ATR-based stop for active trades
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
        # Disabled: ROI table handles all timing exits (guaranteed +0.5% at 90min).
        # Hard -5% stoploss handles catastrophic losses. Time exit was cutting
        # winners early at uncertain market rates (-$0.123 avg vs +$0.212 for ROI).
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
        # NORMAL MODE: Enter when prediction is POSITIVE (model bullish → price will rise)
        if target_val <= 0:
            logger.warning(f"[{pair}] LEA confirm: pred {target_val:.6f} <= 0, DENIED (need positive)")
            return False

        quantile = signal_candle.get("pred_quantile", 0.0)
        # NORMAL MODE: We want top 25% (quantile >= 0.75), so reject if quantile < threshold
        if pd.notna(quantile) and quantile < self.ml_quantile_threshold:
            logger.warning(f"[{pair}] LEA confirm: quantile {quantile:.3f} < {self.ml_quantile_threshold}, DENIED (normal mode wants >= {self.ml_quantile_threshold})")
            return False

        close = float(signal_candle["close"])
        pivot = float(signal_candle["pivot"])
        r1 = float(signal_candle["r1"])
        # Disabled pivot/r1 filter - too restrictive
        # if close <= pivot:
        #     logger.debug(f"[{pair}] LEA confirm: close {close:.8f} <= pivot {pivot:.8f}")
        #     return False
        # if close >= r1:
        #     logger.debug(f"[{pair}] LEA confirm: close {close:.8f} >= r1 {r1:.8f}")
        #     return False

        ema50 = float(signal_candle["ema_50"])
        # Disabled EMA filter
        # if close <= ema50:
        #     logger.debug(f"[{pair}] LEA confirm: close {close:.8f} <= ema50 {ema50:.8f}")
        #     return False

        rsi = float(signal_candle["rsi"])
        # NORMAL: RSI should be < 75 (not overbought) when entering on bullish signal
        if rsi >= 75:
            logger.warning(f"[{pair}] LEA confirm: RSI {rsi:.1f} >= 75 (overbought), DENIED")
            return False

        volume = float(signal_candle["volume"])
        avg_vol = float(dataframe["volume"].rolling(20).mean().iloc[-1])
        # Disabled volume filter
        # if volume < avg_vol * 0.3:
        #     logger.debug(f"[{pair}] LEA confirm: volume {volume:.2f} < 30% avg {avg_vol:.2f}")
        #     return False

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
