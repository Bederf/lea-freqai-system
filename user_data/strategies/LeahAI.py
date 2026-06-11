"""
LEA FreqAI Strategy — LeahAI v4
===============================
Spec date: 2026-06-05
Architecture change vs v3 (directional classifier):
  - TARGET: volatility expansion prediction
    Binary: (future_ATR_12 > current_ATR * 1.05)
    31.8% positive rate on SOL 5m (balanced, not imbalanced)
  - MODEL: XGBoostClassifier (binary:logistic) with scale_pos_weight=2.14
    Compensates for class imbalance (31.8% positive / 68.2% negative)
  - ENTRY GATE: 3-signal independent ensemble
    1. Model: P(vol expansion) > 0.55
    2. BTC macro: %btc_trend > 0 (price above BTC EMA50)
    3. Pair micro: close > ema_50 (pair in local uptrend)
  - ROI: extended hold times for vol expansion strategy
    {0: 5%, 30: 3%, 60: 2%, 120: 1%}
    Gives vol expansion 30-60 min to develop vs 10-20 min in v3

Unchanged from v3:
  - 74 features, no %ret_12 leakage
  - do_predict == 1 quality gate
  - RSI < 70 overbought guard
  - Stoploss: -5% hard stop
  - custom_stoploss, custom_exit (disabled)
  - IDENTIFIER: leah_v3_vol (forces fresh model)

Why volatility as target (vs directional):
  - Directional target: max feature correlation < 3% — pure noise
  - Volatility target: max feature correlation 8-11% — real signal exists
  - 10x improvement in feature-label correlation

Signal independence argument:
  1. Vol expansion: predicted by vol regime features (ATR ratio, volume z-score)
  2. BTC trend: predicted by BTC-specific features (separate price series)
  3. Pair EMA50: predicted by pair's own price momentum
  Three orthogonal information sources, errors are not perfectly correlated

Kill criteria (50 dry-run trades):
  - Expectancy >= $0.10/trade
  - Sharpe >= 0.5
  - No single trade > 15% of total P&L
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

try:
    from binance_research_backtest_loader import BinanceBacktestResearchLoader
    RESEARCH_LOADER_AVAILABLE = True
except ImportError:
    RESEARCH_LOADER_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "Research loader not available - running without Binance research data"
    )

logger = logging.getLogger(__name__)


def _apply_freqai_fallback(dataframe: DataFrame) -> DataFrame:
    """
    Fail-closed fallback when FreqAI cannot build a valid live frame.
    Classifier fallback: probability = 0.0 (no entry).
    """
    dataframe["&-target"] = 0.0
    dataframe["&-target_mean"] = 0.0
    dataframe["&-target_std"] = 0.0
    dataframe["do_predict"] = 0
    dataframe["btc_regime_bull"] = dataframe.get("btc_regime_bull", 0)
    dataframe["%btc_trend"] = dataframe.get("%btc_trend", 0.0)
    return dataframe


def _get_latest_signal_candle(dataframe: DataFrame) -> pd.Series:
    """
    FreqAI leaves the newest in-progress candle with zero target and do_predict=0.
    Confirm entries against the latest completed candle instead.
    """
    if len(dataframe) == 0:
        return pd.Series(dtype=float)
    if len(dataframe) == 1:
        return dataframe.iloc[-1]
    return dataframe.iloc[-2]


class LeahAIStrategy(IStrategy):
    """
    LEA v4 — Volatility expansion classifier.
    Predicts P(ATR will expand > 5% in next 12 candles).
    Entry fires when vol expansion likely AND BTC trend positive AND pair above EMA50.
    """

    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "5m"
    startup_candle_count = 200

    # =========================================================================
    # ENTRY THRESHOLD — v4
    # =========================================================================
    ml_entry_probability = 0.55    # Model confidence for vol expansion

    # =========================================================================
    # ROI & STOPLOSS — v4
    # Extended hold times: vol expansion needs 30-60 min to develop
    # =========================================================================
    minimal_roi = {
        "0":   0.05,   # 5% immediate (tight but acceptable for vol spike)
        "30":  0.03,   # 3% after 30 min
        "60":  0.02,   # 2% after 60 min
        "120": 0.01,   # 1% after 2 hours (trailing floor)
    }

    stoploss = -0.05
    trailing_stop = False
    use_custom_stoploss = False

    use_exit_signal = False
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    process_only_new_candles = True

    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    atr_period = 14
    atr_multiplier = 1.5

    @property
    def plot_config(self):
        return {
            "main_plot": {
                "ema_50":  {"color": "blue"},
                "ema_200": {"color": "orange"},
            },
            "subplots": {
                "RSI":           {"rsi": {"color": "red"}},
                "MACD":          {"macd": {"color": "blue"}, "macdsignal": {"color": "orange"}},
                "Probability":   {"&-target": {"color": "green"}},
                "BTC Trend":     {"%btc_trend": {"color": "purple"}},
                "ATR Ratio":     {"%atr_ratio": {"color": "teal"}},
            },
        }

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._atr_cache: dict[str, float] = {}
        self.research_loader = None
        self.research_data_cache = {}
        if RESEARCH_LOADER_AVAILABLE:
            try:
                self.research_loader = BinanceBacktestResearchLoader()
                logger.info("Research loader initialised")
            except Exception as e:
                logger.warning(f"Failed to initialise research loader: {e}")

    # =========================================================================
    # FEATURE ENGINEERING — unchanged from v3
    # =========================================================================

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        # Price momentum
        dataframe["%ret_1"] = dataframe["close"].pct_change(1)
        dataframe["%ret_3"] = dataframe["close"].pct_change(3)
        dataframe["%ret_6"] = dataframe["close"].pct_change(6)
        # %ret_12 EXCLUDED — feature-target leakage

        # Volatility
        dataframe["atr14"]      = ta.ATR(dataframe, timeperiod=14)
        dataframe["%atr14_rel"] = dataframe["atr14"] / dataframe["close"]
        dataframe["%atr_ratio"] = (
            dataframe["atr14"] / dataframe["atr14"].rolling(20).mean()
        )

        # Range
        dataframe["%rng_24"] = (
            dataframe["high"].rolling(24).max() - dataframe["low"].rolling(24).min()
        ) / dataframe["close"]

        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=2
        )
        dataframe["bb_lowerband"]  = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"]  = bollinger["upper"]
        dataframe["%bb_width"]     = (
            (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
            / dataframe["bb_middleband"]
        )
        dataframe["%bb_position"]  = (
            (dataframe["close"] - dataframe["bb_lowerband"])
            / (dataframe["bb_upperband"] - dataframe["bb_lowerband"] + 1e-9)
        )

        # Z-score
        returns = dataframe["close"].pct_change()
        dataframe["%z_48"] = (
            (returns - returns.rolling(48).mean())
            / (returns.rolling(48).std() + 1e-9)
        )

        # Volume
        dataframe["%vol_z_48"]  = (
            (dataframe["volume"] - dataframe["volume"].rolling(48).mean())
            / (dataframe["volume"].rolling(48).std() + 1e-9)
        )
        dataframe["%vol_ratio"] = (
            dataframe["volume"] / (dataframe["volume"].rolling(20).mean() + 1e-9)
        )

        # Momentum oscillators
        dataframe["rsi"]        = ta.RSI(dataframe, timeperiod=14)
        dataframe["%rsi_delta"] = dataframe["rsi"].diff(3)

        macd = ta.MACD(dataframe)
        dataframe["macd"]       = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"]   = macd["macdhist"]
        dataframe["%macd_rel"]  = dataframe["macd"] / (dataframe["close"] + 1e-9)

        # Trend EMAs
        dataframe["ema_50"]       = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"]      = ta.EMA(dataframe, timeperiod=200)
        dataframe["%ema50_dev"]   = (dataframe["close"] - dataframe["ema_50"]) / dataframe["ema_50"]
        dataframe["%ema200_dev"]  = (dataframe["close"] - dataframe["ema_200"]) / dataframe["ema_200"]

        # Candle body character
        dataframe["%body_size"]  = (
            (dataframe["close"] - dataframe["open"]).abs()
            / (dataframe["high"] - dataframe["low"] + 1e-9)
        )
        dataframe["%upper_wick"] = (
            (dataframe["high"] - dataframe[["close", "open"]].max(axis=1))
            / (dataframe["high"] - dataframe["low"] + 1e-9)
        )

        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        dataframe = self.feature_engineering_expand_all(
            dataframe, period=1, metadata=metadata
        )
        return dataframe

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        BTC macro regime features.
        %btc_trend is the v4 entry gate — not btc_regime_bull.
        """
        if metadata.get("pair") != "BTC/USDT" and self.dp:
            btc = self.dp.get_pair_dataframe(pair="BTC/USDT", timeframe=self.timeframe)
            if not btc.empty and len(btc) > 50:
                btc_ema8  = ta.EMA(btc["close"], timeperiod=8)
                btc_ema21 = ta.EMA(btc["close"], timeperiod=21)
                btc_regime = pd.Series((btc_ema8 > btc_ema21).astype(int), index=btc["close"].index)

                btc_ema50   = ta.EMA(btc["close"], timeperiod=50)
                btc_trend   = pd.Series((btc["close"] - btc_ema50) / (btc_ema50 + 1e-9), index=btc["close"].index)
                btc_roc3    = pd.Series(btc["close"].pct_change(3), index=btc["close"].index)
                btc_vol48   = pd.Series(btc["close"].pct_change().rolling(48).std(), index=btc["close"].index)
                btc_atr14   = ta.ATR(btc, timeperiod=14)
                btc_atr_rel = pd.Series(btc_atr14 / (btc["close"] + 1e-9), index=btc["close"].index)
                btc_vol_ratio = pd.Series(btc["volume"] / (btc["volume"].rolling(20).mean() + 1e-9), index=btc["close"].index)
                btc_bb = qtpylib.bollinger_bands(
                    qtpylib.typical_price(btc), window=20, stds=2
                )
                btc_bb_width = pd.Series(
                    (btc_bb["upper"] - btc_bb["lower"]) / (btc_bb["mid"] + 1e-9),
                    index=btc["close"].index
                )

                idx = dataframe.index
                dataframe["btc_regime_bull"]  = btc_regime.reindex(idx, method="ffill").fillna(0).astype(int)
                dataframe["%btc_trend"]       = btc_trend.reindex(idx, method="ffill").fillna(0.0)
                dataframe["%btc_roc_3"]        = btc_roc3.reindex(idx, method="ffill").fillna(0.0)
                dataframe["%market_vol"]       = btc_vol48.reindex(idx, method="ffill").fillna(0.0)
                dataframe["%btc_atr_rel"]        = btc_atr_rel.reindex(idx, method="ffill").fillna(0.0)
                dataframe["%btc_vol_ratio"]    = btc_vol_ratio.reindex(idx, method="ffill").fillna(1.0)
                dataframe["%btc_bb_width"]      = btc_bb_width.reindex(idx, method="ffill").fillna(0.0)
            else:
                logger.warning("BTC/USDT informative unavailable — regime defaults to 0")
                dataframe["btc_regime_bull"]  = 0
                dataframe["%btc_trend"]       = 0.0
                dataframe["%btc_roc_3"]        = 0.0
                dataframe["%market_vol"]      = dataframe["close"].pct_change().rolling(48).std()
                dataframe["%btc_atr_rel"]       = 0.0
                dataframe["%btc_vol_ratio"]   = 1.0
                dataframe["%btc_bb_width"]    = 0.0
        else:
            dataframe["btc_regime_bull"]  = 1
            dataframe["%btc_trend"]       = 0.0
            dataframe["%btc_roc_3"]        = dataframe["close"].pct_change(3)
            dataframe["%market_vol"]      = dataframe["close"].pct_change().rolling(48).std()
            dataframe["%btc_atr_rel"]     = ta.ATR(dataframe, timeperiod=14) / dataframe["close"]
            dataframe["%btc_vol_ratio"]   = dataframe["volume"] / dataframe["volume"].rolling(20).mean()
            dataframe["%btc_bb_width"]    = 0.0

        return dataframe

    # =========================================================================
    # TARGET — v4 CHANGE
    # Volatility expansion: ATR in 12 candles > current ATR * 1.05
    # Positive rate: 31.8% — balanced for binary classification
    # FreqAI XGBoost does NOT auto-binarize — must be explicit here.
    # =========================================================================

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        # Compute ATR here since it may not be populated before set_freqai_targets is called
        if "atr14" not in dataframe.columns:
            dataframe["atr14"] = ta.ATR(dataframe, timeperiod=14)
        future_atr = dataframe["atr14"].shift(-12)
        dataframe["&-target"] = (future_atr > dataframe["atr14"] * 1.05).astype(int)
        return dataframe

    # =========================================================================
    # INDICATORS
    # =========================================================================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        try:
            dataframe = self.freqai.start(dataframe, metadata, self)
        except Exception as exc:
            pair = metadata.get("pair", "UNKNOWN")
            import traceback
            tb = traceback.format_exc()
            logger.warning(
                f"[{pair}] FreqAI prediction failed ({exc.__class__.__name__}: {exc}). "
                f"Fail-closed fallback applied.\nTraceback: {tb}"
            )
            dataframe = _apply_freqai_fallback(dataframe)

        # Re-fetch BTC data and recompute %btc_trend — FreqAI's
        # attach_return_values_to_return_dataframe concatenates model outputs
        # (which include %btc_trend=0 for every row) and overwrites the real
        # values computed in feature_engineering_standard inside FreqAI.
        # Since %btc_trend is not in historic_predictions, FreqAI adds a zeroed
        # column that replaces the correct values. Recompute here to fix.
        if metadata.get("pair") != "BTC/USDT" and self.dp:
            btc = self.dp.get_pair_dataframe(pair="BTC/USDT", timeframe=self.timeframe)
            if not btc.empty and len(btc) > 50:
                btc_ema50 = ta.EMA(btc["close"], timeperiod=50)
                btc_trend = (btc["close"] - btc_ema50) / (btc_ema50 + 1e-9)
                dataframe["%btc_trend"] = btc_trend.reindex(
                    dataframe.index, method="ffill"
                ).fillna(0.0)
            else:
                dataframe["%btc_trend"] = 0.0
        else:
            dataframe["%btc_trend"] = 0.0

        # Recompute indicators for entry/exit logic
        dataframe["rsi"]     = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_50"]  = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["atr"]     = ta.ATR(dataframe, timeperiod=self.atr_period)

        macd = ta.MACD(dataframe)
        dataframe["macd"]       = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"]   = macd["macdhist"]

        dataframe["vol_mean_20"] = dataframe["volume"].rolling(20).mean()

        # Diagnostic logging — fail silently on missing columns
        try:
            if 1 in dataframe.columns:
                prob = dataframe[1]  # col "1" = model P(vol expansion), not&-target (training label)
                btc_trend = float(dataframe["%btc_trend"].iloc[-1]) if "%btc_trend" in dataframe.columns and not pd.isna(dataframe["%btc_trend"].iloc[-1]) else 0.0
                above_ema50 = bool((dataframe["close"].iloc[-1] > dataframe["ema_50"].iloc[-1]) if "ema_50" in dataframe.columns and not pd.isna(dataframe["ema_50"].iloc[-1]) else False)
                do_predict_val = dataframe["do_predict"].iloc[-1] if "do_predict" in dataframe.columns else 'N/A'
                logger.info(
                    f"[{metadata['pair']}] prob: min={prob.min():.4f} max={prob.max():.4f} "
                    f"mean={prob.mean():.4f} last={prob.iloc[-1]:.4f} | "
                    f"btc_trend={btc_trend:+.4f} | above_ema50={above_ema50} | "
                    f"do_predict={do_predict_val} | threshold={self.ml_entry_probability}"
                )
        except Exception:
            pass

        return dataframe

    # =========================================================================
    # ENTRY LOGIC — v4
    # 3-signal independent ensemble:
    #   1. Model: P(vol expansion) > 0.55
    #   2. BTC macro: %btc_trend > 0
    #   3. Pair micro: close > ema_50
    # =========================================================================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        v4 entry conditions:
          1. P(vol expansion) > 0.55
          2. %btc_trend > 0 (BTC bull regime)
          3. close > ema_50 (pair in local uptrend)

        Removed vs v3:
          - btc_regime_bull filter replaced with %btc_trend (continuous)
          - RSI < 70 gate removed (overbought consistent with vol expansion)
        """
        if "&-target" not in dataframe.columns:
            logger.warning(f"[{metadata['pair']}] No &-target column — no entries")
            dataframe["enter_long"] = 0
            return dataframe

        # Guard: require %btc_trend column (created by feature_engineering_standard)
        # If missing (FreqAI fallback active or feature engineering failed), deny entries
        if "%btc_trend" not in dataframe.columns:
            dataframe["enter_long"] = 0
            return dataframe

        conditions = [
            # 1. Model confidence > 55%, vectorized per-row. Live loop reads last row; backtests get correct per-candle values.
            # Fail closed if column 1 missing — &-target is a 0/1 label, not a probability; comparing it to 0.55 silently passes label=1.
            (dataframe[1] > self.ml_entry_probability if 1 in dataframe.columns else pd.Series(False, index=dataframe.index)),

            # 2. BTC bull regime (continuous, not binary)
            dataframe["%btc_trend"] >= 0.002,

            # 3. Pair in local uptrend
            dataframe["close"] > dataframe["ema_50"],

            # 4. FreqAI quality gate
            (
                dataframe["do_predict"] == 1
                if "do_predict" in dataframe.columns
                else pd.Series(True, index=dataframe.index)
            ),

            # 5. Valid candle
            dataframe["volume"] > 0,
        ]

        entry_signal = reduce(lambda x, y: x & y, conditions)
        dataframe["enter_long"] = 0
        dataframe.loc[entry_signal, "enter_long"] = 1

        # Debug: log each condition's last-row result
        cond1 = dataframe[1].iloc[-1] > self.ml_entry_probability if 1 in dataframe.columns else False
        cond2 = dataframe["%btc_trend"].iloc[-1] >= 0.002 if "%btc_trend" in dataframe.columns else False
        cond3 = dataframe["close"].iloc[-1] > dataframe["ema_50"].iloc[-1] if "ema_50" in dataframe.columns else False
        cond4 = dataframe["do_predict"].iloc[-1] == 1 if "do_predict" in dataframe.columns else False
        cond5 = dataframe["volume"].iloc[-1] > 0 if "volume" in dataframe.columns else False
        _prob = dataframe[1].iloc[-1] if 1 in dataframe.columns else float("nan")
        logger.warning(f"[{metadata['pair']}] entry check: prob={_prob:.4f} vs {self.ml_entry_probability}, cond1={cond1}, cond2={cond2}, cond3={cond3}, cond4={cond4}, cond5={cond5}")

        # Debug: log entry signal status
        if dataframe["enter_long"].iloc[-1]:
            logger.warning(f"[{metadata['pair']}] populate_entry_signals TRIGGERED — enter_long=True")
        else:
            logger.warning(f"[{metadata['pair']}] populate_entry_signals NOT triggered — enter_long=False")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """ROI table drives all exits. Exit signal disabled."""
        dataframe["exit_long"] = 0
        return dataframe

    # =========================================================================
    # EXIT LOGIC — unchanged from v4 spec
    # =========================================================================

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        if current_time - trade.open_date_utc >= timedelta(minutes=90):
            return self.stoploss

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

        if current_profit > 0.030:
            stop_price = max(entry_price * 0.995, stop_price)
            stop_pct = (stop_price / entry_price) - 1
        elif current_profit > 0.015:
            stop_price = max(entry_price * 0.998, stop_price)
            stop_pct = (stop_price / entry_price) - 1
        elif current_profit > 0.008:
            stop_price = entry_price - (stop_distance * 0.5)
            stop_pct = (stop_price / entry_price) - 1

        return max(stop_pct, -abs(self.stoploss))

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        # Time-based exit: if underwater after 6 hours, exit rather than hold indefinitely
        if current_profit < 0:
            hold_minutes = (current_time - trade.open_date).total_seconds() / 60
            if hold_minutes > 360:  # 6 hours
                return "time_exit_6h_negative"
        return None

    # =========================================================================
    # TRADE CONFIRMATION — v4
    # =========================================================================

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
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return False

        signal_candle = _get_latest_signal_candle(dataframe)

        if "&-target" not in dataframe.columns:
            return False

        # Gate 1: probability threshold
        prob = float(signal_candle[1])
        if prob <= self.ml_entry_probability:
            logger.warning(
                f"[{pair}] confirm DENIED: prob={prob:.4f} <= {self.ml_entry_probability}"
            )
            return False

        # Gate 2: BTC trend — require meaningful positive regime, not noise
        btc_trend = float(signal_candle.get("%btc_trend", 0))
        if btc_trend < 0.002:
            logger.warning(f"[{pair}] confirm DENIED: BTC trend={btc_trend:+.4f} < 0.002")
            return False

        # Gate 3: pair above EMA50
        ema_50 = float(signal_candle.get("ema_50", 0))
        close = float(signal_candle.get("close", 0))
        if ema_50 > 0 and close <= ema_50:
            logger.warning(f"[{pair}] confirm DENIED: close={close:.4f} <= ema_50={ema_50:.4f}")
            return False

        logger.info(
            f"[{pair}] confirm APPROVED: prob={prob:.4f} btc_trend={btc_trend:+.4f} close={close:.4f} above_ema50"
        )
        return True

    # =========================================================================
    # POSITION SIZING — v4
    # Scaled by probability of vol expansion.
    # =========================================================================

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
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return proposed_stake

        signal_candle = _get_latest_signal_candle(dataframe)
        if "&-target" not in dataframe.columns:
            return proposed_stake

        prob = float(signal_candle[1])
        confidence_multiplier = np.clip(1.0 + (prob - self.ml_entry_probability) * 2.5, 0.5, 1.5)
        return np.clip(proposed_stake * confidence_multiplier, min_stake, max_stake)