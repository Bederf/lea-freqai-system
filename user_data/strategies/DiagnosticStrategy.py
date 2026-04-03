"""
Diagnostic Strategy - Minimal filters to identify blocking conditions
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

logger = logging.getLogger(__name__)


def _apply_freqai_fallback(dataframe: DataFrame) -> DataFrame:
    """
    Keep diagnostics running even when FreqAI cannot hydrate pair history.
    The fallback suppresses entries until valid predictions return.
    """
    dataframe["&-target"] = 0.0
    dataframe["do_predict"] = 0
    return dataframe


def _get_latest_signal_candle(dataframe: DataFrame) -> pd.Series:
    """
    Use the latest completed candle for live decisions.
    The newest row can still be forming and may drift between callbacks.
    """
    if len(dataframe) == 0:
        return pd.Series(dtype=float)
    if len(dataframe) == 1:
        return dataframe.iloc[-1]
    return dataframe.iloc[-2]


class DiagnosticStrategy(IStrategy):
    """
    Ultra-minimal strategy to diagnose what's blocking trades
    """

    INTERFACE_VERSION = 3
    can_short = False
    timeframe = "5m"
    startup_candle_count = 200
    ml_entry_threshold = 0.0005
    stale_trade_hours = 8
    max_trade_hours = 18

    # Very aggressive ROI
    minimal_roi = {
        "0": 0.05,   # 5%
        "30": 0.02,  # 2%
        "60": 0.01   # 1%
    }

    stoploss = -0.10
    trailing_stop = False
    # Keep dataframe exits neutral, but enable custom_exit() for stale-trade cleanup.
    use_exit_signal = True
    exit_profit_only = False
    process_only_new_candles = True

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

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.risk_state = {}

    def calculate_signal_confidence(self, metrics: dict) -> dict:
        total = metrics["total_candles"]
        if total == 0:
            return {
                "confidence_score": 0.0,
                "allow_trade": False,
                "risk_multiplier": 0.0,
                "rsi_health": 0.0,
                "ema_alignment": 0.0,
                "positive_ratio": 0.0,
                "strong_ratio": 0.0,
            }

        strong = metrics["pred_strong"] / total
        positive = metrics["pred_positive"] / total
        rsi = metrics["rsi_ok"] / total
        ema = metrics["price_above_ema"] / total

        confidence_score = (
            0.40 * strong +
            0.25 * positive +
            0.20 * rsi +
            0.15 * ema
        )

        if confidence_score < 0.40:
            allow_trade = False
            multiplier = 0.0
        elif confidence_score < 0.60:
            allow_trade = True
            multiplier = 0.25
        elif confidence_score < 0.75:
            allow_trade = True
            multiplier = 0.5
        else:
            allow_trade = True
            multiplier = 1.0

        return {
            "confidence_score": confidence_score,
            "allow_trade": allow_trade,
            "risk_multiplier": multiplier,
            "rsi_health": rsi,
            "ema_alignment": ema,
            "positive_ratio": positive,
            "strong_ratio": strong,
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
        try:
            dataframe = self.freqai.start(dataframe, metadata, self)
        except (IndexError, KeyError) as exc:
            pair = metadata.get("pair", "UNKNOWN")
            logger.warning(
                f"[{pair}] FreqAI live history unavailable ({exc.__class__.__name__}: {exc}). "
                "Using fail-closed fallback frame."
            )
            dataframe = _apply_freqai_fallback(dataframe)
            self.risk_state[pair] = {
                "confidence_score": 0.0,
                "allow_trade": False,
                "risk_multiplier": 0.0,
                "rsi_health": 0.0,
                "ema_alignment": 0.0,
                "positive_ratio": 0.0,
                "strong_ratio": 0.0,
            }

        # Recompute indicators (FreqAI doesn't preserve non-% prefixed columns)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)

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

            metrics = {
                "total_candles": total_candles,
                "pred_positive": pred_positive_count,
                "pred_strong": pred_strong_count,
                "rsi_ok": rsi_ok_count,
                "price_above_ema": price_above_ema_count,
            }
            signal = self.calculate_signal_confidence(metrics)
            self.risk_state[metadata["pair"]] = signal

            # expose latest metrics for logging or debugging
            for name, value in signal.items():
                dataframe[f"{name}"] = value
            dataframe["confidence_usd"] = signal["confidence_score"]

            last_target = dataframe["&-target"].iloc[-1] if "&-target" in dataframe.columns else 0.0
            logger.info(
                "gate_summary "
                f"pair={metadata.get('pair', 'UNKNOWN')} "
                f"target={last_target:.6f} "
                f"pred_positive={signal['positive_ratio']:.3f} "
                f"pred_strong={signal['strong_ratio']:.3f} "
                f"rsi_health={signal['rsi_health']:.3f} "
                f"ema_align={signal['ema_alignment']:.3f} "
                f"confidence={signal['confidence_score']:.3f} "
                f"allow_trade={'yes' if signal['allow_trade'] else 'no'} "
                f"risk_multiplier={signal['risk_multiplier']:.2f}"
            )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry requires a meaningful positive prediction plus basic live confirmation.
        """
        signal = self.risk_state.get(metadata["pair"], None)

        if "&-target" not in dataframe.columns or signal is None:
            dataframe["enter_long"] = 0
            return dataframe

        allow_trade = signal["allow_trade"]

        if not allow_trade:
            dataframe["enter_long"] = 0
            logger.info(
                "buy_blocked "
                f"pair={metadata.get('pair','UNKNOWN')} "
                f"confidence={signal['confidence_score']:.3f} "
                f"threshold=0.40"
            )
            return dataframe

        dataframe["enter_long"] = 0

        ml_signal = dataframe["&-target"] > self.ml_entry_threshold
        trend_signal = dataframe["close"] > dataframe["ema_50"]

        conditions = [ml_signal, trend_signal]

        do_predict_signal = None
        if "do_predict" in dataframe.columns:
            do_predict_signal = dataframe["do_predict"] == 1
            conditions.append(do_predict_signal)

        entry_signal = reduce(lambda x, y: x & y, conditions)
        dataframe.loc[entry_signal, "enter_long"] = 1

        pair = metadata.get("pair", "UNKNOWN")
        signal_candle = _get_latest_signal_candle(dataframe)
        signal_idx = signal_candle.name if not signal_candle.empty else None
        live_idx = dataframe.index[-1] if len(dataframe) > 0 else None
        if len(dataframe) > 1 and signal_idx is not None and live_idx is not None:
            dataframe.at[live_idx, "enter_long"] = int(bool(entry_signal.loc[signal_idx]))

        summary = (
            "entry_gate_summary "
            f"pair={pair} "
            f"threshold={self.ml_entry_threshold:.4f} "
            f"target_signal={float(signal_candle['&-target']) if signal_idx is not None else 0.0:.6f} "
            f"ml_pass={int(ml_signal.sum())}/{len(dataframe)} "
            f"trend_pass={int(trend_signal.sum())}/{len(dataframe)} "
        )
        if do_predict_signal is not None:
            summary += f"do_predict_pass={int(do_predict_signal.sum())}/{len(dataframe)} "
        summary += f"entry_pass={int(entry_signal.sum())}/{len(dataframe)}"
        logger.info(summary)

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Keep dataframe exits neutral and use custom_exit() for age-based cleanup.
        """
        dataframe["exit_long"] = 0
        return dataframe

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | bool | None:
        result = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        dataframe = result[0] if isinstance(result, tuple) else result
        if dataframe.empty or "&-target" not in dataframe.columns:
            return None

        last_candle = _get_latest_signal_candle(dataframe)
        trade_age = current_time - trade.open_date_utc
        weak_prediction = float(last_candle["&-target"]) <= 0.0
        lost_trend = float(last_candle["close"]) <= float(last_candle["ema_50"])

        if trade_age >= timedelta(hours=self.max_trade_hours):
            logger.info(
                "custom_exit "
                f"pair={pair} "
                "reason=max_trade_hours "
                f"age_hours={trade_age.total_seconds() / 3600:.1f} "
                f"profit={current_profit:.4f}"
            )
            return "max_trade_hours"

        if (
            trade_age >= timedelta(hours=self.stale_trade_hours)
            and current_profit < 0.002
            and (weak_prediction or lost_trend)
        ):
            logger.info(
                "custom_exit "
                f"pair={pair} "
                "reason=stale_weak_setup "
                f"age_hours={trade_age.total_seconds() / 3600:.1f} "
                f"profit={current_profit:.4f} "
                f"target={float(last_candle['&-target']):.6f} "
                f"trend_ok={'yes' if not lost_trend else 'no'}"
            )
            return "stale_weak_setup"

        return None

    def custom_stake_amount(self, pair: str, current_time, current_rate, proposed_stake, **kwargs) -> float:
        signal = self.risk_state.get(pair)
        if not signal:
            return proposed_stake
        multiplier = signal.get("risk_multiplier", 1.0)
        adjusted = max(proposed_stake * multiplier, 0.0)
        if adjusted != proposed_stake:
            logger.info(
                "stake_adjusted "
                f"pair={pair} "
                f"proposed={proposed_stake:.6f} "
                f"adjusted={adjusted:.6f} "
                f"multiplier={multiplier:.2f}"
            )
        return adjusted

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        """
        Align final confirmation with the live entry gate.
        """
        result = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        dataframe = result[0] if isinstance(result, tuple) else result
        if dataframe.empty:
            return False
        last_candle = _get_latest_signal_candle(dataframe)

        if "&-target" not in dataframe.columns:
            return False
        if last_candle["&-target"] <= self.ml_entry_threshold:
            return False
        if "do_predict" in dataframe.columns and last_candle["do_predict"] != 1:
            return False
        if last_candle["close"] <= last_candle["ema_50"]:
            return False

        return True
