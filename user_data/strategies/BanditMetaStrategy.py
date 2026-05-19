"""
Integrated Contextual Bandit Meta-Strategy for Freqtrade

Combines:
- Bandit Q-value strategy selection (LEA vs Hybrid/FinAgent)
- Quantile-filtered ML entry (top 20% predictions only)
- Pivot-based entry filters (bullish bias, resistance avoidance)
- ATR-based dynamic stop-loss
- Time-horizon exits (60 min LEA, 90 min Hybrid/FinAgent)
- Pivot take-profit (R1 for LEA, R2 for Hybrid)
- Partial take-profit via early ROI tiers

Backtest: row-wise deterministic exploitation (no epsilon noise)
Live/dry-run: epsilon-greedy exploration with Q-values
"""

import json
import logging
from datetime import datetime, timedelta
from functools import reduce
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.enums import RunMode
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)


class BanditMetaStrategy(IStrategy):
    INTERFACE_VERSION = 3
    can_short = False

    timeframe = "5m"
    startup_candle_count = 200
    process_only_new_candles = True

    # =====================================================================
    # ML THRESHOLDS & QUANTILES
    # =====================================================================
    lea_entry_threshold = 0.01
    hybrid_entry_threshold = 0.01
    ml_quantile_threshold = 0.80  # Top 20% of predictions only

    # =====================================================================
    # ATR STOP-LOSS
    # =====================================================================
    atr_period = 14
    atr_multiplier = 1.5  # Stop distance = ATR × multiplier

    # =====================================================================
    # TIME HORIZONS
    # =====================================================================
    lea_max_hold_minutes = 240
    hybrid_max_hold_minutes = 240

    # =====================================================================
    # PARTIAL TAKE-PROFIT (via early ROI tiers)
    # =====================================================================
    # First tier takes 50% off at 1% profit, second tier takes remaining at R1/R2 or time
    # partial_tp_pct = 0.5 is informational; actual partial TP is handled by minimal_roi
    partial_tp_enabled = True
    partial_tp_profit = 0.01  # First partial exit at this profit

    # =====================================================================
    # ROI & STOPLOSS
    # =====================================================================
    # Partial TP: first tier takes ~50% at 1%, second tier runs until pivot/time
    minimal_roi = {
        "0": 0.015,   # Immediate profit - aggressive entry
        "30": 0.010,  # 1% after 30 min
        "60": 0.008,  # 0.8% after 1 hour (partial exit opportunity)
        "120": 0.005, # 0.5% after 2 hours
    }

    stoploss = -0.05
    trailing_stop = False
    use_custom_stoploss = True  # Enable for ATR-based dynamic stop

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    order_time_in_force = {
        "entry": "GTC",
        "exit": "GTC",
    }

    def __init__(self, config: dict):
        super().__init__(config)

        self.selector_path = Path("user_data/bandit_selector.json")
        self.selection_log_path = Path("user_data/bandit_selections.jsonl")
        self.load_selector()

        # Store per-pair ATR values for dynamic stop-loss
        self._atr_cache: dict[str, float] = {}

        logger.info("BanditMetaStrategy initialized (integrated version)")
        logger.info(
            "Selector loaded with %s contexts",
            len(self.selector.get("contexts", {})),
        )

    # =====================================================================
    # SELECTOR LOADING / LOGGING
    # =====================================================================

    def load_selector(self) -> None:
        """Load contextual bandit selector table or initialize defaults."""
        if self.selector_path.exists():
            try:
                with open(self.selector_path, "r", encoding="utf-8") as f:
                    self.selector = json.load(f)
                logger.info("Loaded selector from %s", self.selector_path)
            except Exception as e:
                logger.error("Failed to load selector: %s", e)
                self.selector = self._default_selector()
        else:
            self.selector = self._default_selector()
            logger.warning("No selector found at %s, using defaults", self.selector_path)
            logger.warning("Run trades and meta_learner.py to build Q-values")

    def _default_selector(self) -> dict:
        return {
            "contexts": {},
            "epsilon": 0.1,
            "alpha": 0.1,
            "last_updated": None,
            "total_trades_processed": 0,
        }

    def log_selection(self, pair: str, context: str, strategy: str, entry_tag: str) -> None:
        """Log only confirmed trade selections."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "pair": pair,
            "context": context,
            "strategy": strategy,
            "entry_tag": entry_tag,
        }
        try:
            with open(self.selection_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error("Failed to log selection: %s", e)

    def log_event(self, event_type: str, payload: dict) -> None:
        """Structured observability log for signal/confirm/exit lifecycle events."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            **payload,
        }
        try:
            with open(self.selection_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error("Failed to log event '%s': %s", event_type, e)

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        """Best-effort float conversion for telemetry payloads."""
        if pd.isna(value):
            return None
        try:
            return float(value)
        except Exception:
            return None

    # =====================================================================
    # PREDICTION COLUMN HELPERS
    # =====================================================================

    def _get_prediction_column(self, dataframe: DataFrame) -> Optional[str]:
        """Resolve the FreqAI prediction column."""
        candidates = ["&-target", "prediction", "predicted_return", "target"]
        for col in candidates:
            if col in dataframe.columns:
                return col
        return None

    def _prediction_available(self, dataframe: DataFrame) -> bool:
        pred_col = self._get_prediction_column(dataframe)
        return pred_col is not None

    # =====================================================================
    # RUN MODE HELPERS
    # =====================================================================

    def _use_bandit_exploration(self) -> bool:
        """Epsilon-greedy exploration only in live and dry-run."""
        rm = self.config.get("runmode")
        return rm in (RunMode.LIVE, RunMode.DRY_RUN)

    def _use_rowwise_bandit(self) -> bool:
        """Per-candle context + deterministic arm in backtest and hyperopt."""
        rm = self.config.get("runmode")
        return rm in (RunMode.BACKTEST, RunMode.HYPEROPT)

    # =====================================================================
    # CONTEXT / BANDIT SELECTION
    # =====================================================================

    def get_context(self, dataframe: DataFrame, pair: str) -> str:
        """Extract current context from the latest candle."""
        if len(dataframe) < 50:
            return "vol_med_trend_flat_hour_day"

        last = dataframe.iloc[-1]

        # 1. Volatility regime
        if "%market_vol" in dataframe.columns and pd.notna(last.get("%market_vol", np.nan)):
            market_vol = last["%market_vol"]
            if market_vol < 0.02:
                vol_regime = "low"
            elif market_vol > 0.05:
                vol_regime = "high"
            else:
                vol_regime = "med"
        else:
            returns = dataframe["close"].pct_change()
            vol = returns.rolling(48).std().iloc[-1]
            if pd.isna(vol):
                vol_regime = "med"
            elif vol < 0.02:
                vol_regime = "low"
            elif vol > 0.05:
                vol_regime = "high"
            else:
                vol_regime = "med"

        # 2. Trend regime
        if "ema_50" in dataframe.columns and pd.notna(last.get("ema_50", np.nan)):
            ema50 = last["ema_50"]
            close = last["close"]
            if ema50 > 0:
                trend = (close - ema50) / ema50
                if trend < -0.02:
                    trend_regime = "down"
                elif trend > 0.02:
                    trend_regime = "up"
                else:
                    trend_regime = "flat"
            else:
                trend_regime = "flat"
        else:
            trend_regime = "flat"

        # 3. Time of day
        try:
            if hasattr(last.name, "hour"):
                hour = int(last.name.hour)
            else:
                hour = datetime.utcnow().hour
            if hour < 8:
                time_regime = "morning"
            elif hour < 16:
                time_regime = "day"
            else:
                time_regime = "evening"
        except Exception:
            time_regime = "day"

        return f"vol_{vol_regime}_trend_{trend_regime}_hour_{time_regime}"

    def _get_context_series(self, dataframe: DataFrame) -> pd.Series:
        """Per-row context strings for backtest/hyperopt."""
        default_ctx = "vol_med_trend_flat_hour_day"
        n = len(dataframe)
        idx = dataframe.index
        if n < 50:
            return pd.Series([default_ctx] * n, index=idx)

        # Volatility regime
        returns = dataframe["close"].pct_change()
        roll_vol = returns.rolling(48).std()
        if "%market_vol" in dataframe.columns:
            mv = dataframe["%market_vol"]
            v = mv.where(mv.notna(), roll_vol)
        else:
            v = roll_vol
        vol_regime = np.where(
            pd.isna(v), "med",
            np.where(v < 0.02, "low", np.where(v > 0.05, "high", "med")),
        )

        # Trend regime
        if "ema_50" in dataframe.columns:
            ema50 = dataframe["ema_50"]
            close = dataframe["close"]
            denom = ema50.replace(0, np.nan)
            trend_pct = (close - ema50) / denom
            trend_regime = np.where(
                ema50 <= 0, "flat",
                np.where(
                    pd.isna(trend_pct), "flat",
                    np.where(
                        trend_pct < -0.02, "down",
                        np.where(trend_pct > 0.02, "up", "flat"),
                    ),
                ),
            )
        else:
            trend_regime = np.full(n, "flat", dtype=object)

        # Time of day
        try:
            if hasattr(idx, "hour"):
                hours = idx.hour.to_numpy()
            else:
                h = datetime.utcnow().hour
                hours = np.full(n, h, dtype=int)
            time_regime = np.where(
                hours < 8, "morning",
                np.where(hours < 16, "day", "evening"),
            )
        except Exception:
            time_regime = np.full(n, "day", dtype=object)

        ctx = (
            "vol_"
            + pd.Series(vol_regime, index=idx).astype(str)
            + "_trend_"
            + pd.Series(trend_regime, index=idx).astype(str)
            + "_hour_"
            + pd.Series(time_regime, index=idx).astype(str)
        )
        return ctx

    def _map_context_to_strategy_deterministic(self, context: str) -> str:
        """Exploit Q-values only; unknown context defaults to LEA."""
        if context not in self.selector.get("contexts", {}):
            return "lea"
        ctx_data = self.selector["contexts"][context]
        lea_q = ctx_data.get("LeaFreqAIStrategy", {}).get("q_value", 0.0)
        hybrid_q = ctx_data.get("HybridAIStrategy", {}).get("q_value", 0.0)
        return "lea" if lea_q >= hybrid_q else "hybrid"

    def _strategy_series_from_contexts(self, context_series: pd.Series) -> pd.Series:
        """Map each row's context to lea/hybrid using Q-values."""
        uniq = pd.unique(context_series)
        mapping = {c: self._map_context_to_strategy_deterministic(str(c)) for c in uniq}
        return context_series.map(mapping)

    def select_strategy(self, context: str, pair: str) -> str:
        """Epsilon-greedy exploration (live/dry-run); deterministic exploit otherwise."""
        epsilon = float(self.selector.get("epsilon", 0.1))

        if self._use_bandit_exploration() and np.random.random() < epsilon:
            selected = np.random.choice(["lea", "hybrid"])
            logger.debug("[%s] EXPLORE selected=%s epsilon=%.3f", pair, selected, epsilon)
            return selected

        if context not in self.selector.get("contexts", {}):
            logger.debug("[%s] Unknown context '%s', defaulting to LEA", pair, context)
            return "lea"

        ctx_data = self.selector["contexts"][context]
        lea_q = ctx_data.get("LeaFreqAIStrategy", {}).get("q_value", 0.0)
        hybrid_q = ctx_data.get("HybridAIStrategy", {}).get("q_value", 0.0)

        if lea_q >= hybrid_q:
            logger.debug("[%s] EXPLOIT LEA q=%.5f hybrid_q=%.5f", pair, lea_q, hybrid_q)
            return "lea"

        logger.debug("[%s] EXPLOIT HYBRID q=%.5f lea_q=%.5f", pair, hybrid_q, lea_q)
        return "hybrid"

    # =====================================================================
    # FREQAI FEATURE ENGINEERING
    # =====================================================================

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        dataframe["%ret_1"] = dataframe["close"].pct_change(1)
        dataframe["%ret_3"] = dataframe["close"].pct_change(3)
        dataframe["%ret_12"] = dataframe["close"].pct_change(12)

        dataframe["atr14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["%atr14_rel"] = dataframe["atr14"] / dataframe["close"]

        dataframe["%rng_24"] = (
            dataframe["high"].rolling(24).max() - dataframe["low"].rolling(24).min()
        ) / dataframe["close"]

        returns = dataframe["close"].pct_change()
        dataframe["%z_48"] = (
            (returns - returns.rolling(48).mean()) / returns.rolling(48).std()
        )

        dataframe["%vol_z_48"] = (
            (dataframe["volume"] - dataframe["volume"].rolling(48).mean())
            / dataframe["volume"].rolling(48).std()
        )

        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        from technical import qtpylib

        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=20, stds=2
        )
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["%bb_width"] = (
            (dataframe["bb_upperband"] - dataframe["bb_lowerband"])
            / dataframe["bb_middleband"]
        )

        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        return self.feature_engineering_expand_all(
            dataframe, period=1, metadata=metadata
        )

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        if metadata.get("pair") != "BTC/USDT" and self.dp:
            btc_dataframe = self.dp.get_pair_dataframe(
                pair="BTC/USDT",
                timeframe=self.timeframe,
            )

            if not btc_dataframe.empty and len(btc_dataframe) > 50:
                btc_ema = ta.EMA(btc_dataframe["close"], timeperiod=50)
                btc_trend = (btc_dataframe["close"] - btc_ema) / btc_ema
                btc_vol = btc_dataframe["close"].pct_change().rolling(48).std()

                dataframe["%btc_trend"] = btc_trend.reindex(
                    dataframe.index, method="ffill"
                )
                dataframe["%market_vol"] = btc_vol.reindex(
                    dataframe.index, method="ffill"
                )
            else:
                dataframe["%btc_trend"] = 0.0
                dataframe["%market_vol"] = dataframe["close"].pct_change().rolling(48).std()
        else:
            dataframe["%btc_trend"] = 0.0
            dataframe["%market_vol"] = dataframe["close"].pct_change().rolling(48).std()

        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        dataframe["&-target"] = dataframe["close"].shift(-12).pct_change(12)
        return dataframe

    # =====================================================================
    # INDICATORS
    # =====================================================================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.freqai.start(dataframe, metadata, self)

        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]

        dataframe["vol_mean_20"] = dataframe["volume"].rolling(20).mean()

        # === ATR (for dynamic stop-loss) ===
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=self.atr_period)

        # === Prediction quantile (top X% only) ===
        pred_col = self._get_prediction_column(dataframe)
        if pred_col:
            dataframe["pred_quantile"] = dataframe[pred_col].rank(pct=True)

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

        return dataframe

    # =====================================================================
    # ENTRY LOGIC
    # =====================================================================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata["pair"]
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = None

        pred_col = self._get_prediction_column(dataframe)
        if pred_col is None:
            logger.warning("[%s] No FreqAI prediction column found, no entries", pair)
            return dataframe

        if self._use_rowwise_bandit():
            return self._populate_entry_trend_rowwise(dataframe, metadata, pair, pred_col)

        context = self.get_context(dataframe, pair)
        selected = self.select_strategy(context, pair)

        if selected == "lea":
            dataframe = self._populate_entry_lea(dataframe, metadata, context, pred_col)
        else:
            dataframe = self._populate_entry_hybrid(dataframe, metadata, context, pred_col)

        return dataframe

    def _quantile_filter(self, dataframe: DataFrame, pred_col: str) -> pd.Series:
        """Return mask for top X% predictions (ml_quantile_threshold)."""
        if "pred_quantile" in dataframe.columns:
            return dataframe["pred_quantile"] >= self.ml_quantile_threshold
        # Fallback: use relative ranking
        return dataframe[pred_col] >= dataframe[pred_col].quantile(self.ml_quantile_threshold)

    def _lea_entry_mask(self, dataframe: DataFrame, pred_col: str) -> pd.Series:
        conditions = [
            dataframe[pred_col] > self.lea_entry_threshold,
            self._quantile_filter(dataframe, pred_col),  # Top 20% predictions only
            dataframe["volume"] > 0,
            dataframe["close"] > dataframe["pivot"],      # Bullish bias
            dataframe["close"] < dataframe["r1"],         # Avoid resistance
        ]
        if "do_predict" in dataframe.columns:
            conditions.append(dataframe["do_predict"] == 1)
        return reduce(lambda x, y: x & y, conditions)

    def _hybrid_entry_mask(self, dataframe: DataFrame, pred_col: str) -> pd.Series:
        conditions = [
            dataframe[pred_col] > self.hybrid_entry_threshold,
            self._quantile_filter(dataframe, pred_col),  # Top 20% predictions only
            dataframe["ema_50"] > dataframe["ema_200"],
            dataframe["rsi"] < 70,
            dataframe["macd"] > dataframe["macdsignal"],
            dataframe["volume"] > 0,
            dataframe["close"] > dataframe["pivot"],      # Bullish bias only
        ]
        if "%btc_trend" in dataframe.columns:
            conditions.append(dataframe["%btc_trend"] > -0.05)
        return reduce(lambda x, y: x & y, conditions)

    def _populate_entry_trend_rowwise(
        self,
        dataframe: DataFrame,
        metadata: dict,
        pair: str,
        pred_col: str,
    ) -> DataFrame:
        """Each row: context from that candle, arm from Q-values only, then that arm's rules."""
        context_series = self._get_context_series(dataframe)
        selected_series = self._strategy_series_from_contexts(context_series)
        mask_lea = self._lea_entry_mask(dataframe, pred_col) & (selected_series == "lea")
        mask_hybrid = self._hybrid_entry_mask(dataframe, pred_col) & (
            selected_series == "hybrid"
        )

        dataframe.loc[mask_lea, "enter_long"] = 1
        dataframe.loc[mask_lea, "enter_tag"] = "lea_bandit_ctx_" + context_series[mask_lea].astype(
            str
        )

        dataframe.loc[mask_hybrid, "enter_long"] = 1
        dataframe.loc[mask_hybrid, "enter_tag"] = (
            "hybrid_bandit_ctx_" + context_series[mask_hybrid].astype(str)
        )

        logger.debug(
            "[%s] rowwise bandit: lea_rows=%s hybrid_rows=%s",
            pair,
            int(mask_lea.sum()),
            int(mask_hybrid.sum()),
        )
        return dataframe

    def _populate_entry_lea(
        self,
        dataframe: DataFrame,
        metadata: dict,
        context: str,
        pred_col: str,
    ) -> DataFrame:
        mask = self._lea_entry_mask(dataframe, pred_col)
        tag = f"lea_bandit_ctx_{context}"
        dataframe.loc[mask, "enter_long"] = 1
        dataframe.loc[mask, "enter_tag"] = tag
        return dataframe

    def _populate_entry_hybrid(
        self,
        dataframe: DataFrame,
        metadata: dict,
        context: str,
        pred_col: str,
    ) -> DataFrame:
        mask = self._hybrid_entry_mask(dataframe, pred_col)
        tag = f"hybrid_bandit_ctx_{context}"
        dataframe.loc[mask, "enter_long"] = 1
        dataframe.loc[mask, "enter_tag"] = tag
        return dataframe

    # =====================================================================
    # EXIT LOGIC
    # =====================================================================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Keep dataframe exit neutral; use custom_exit() for all trade-specific exits."""
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

        # Cache ATR for the pair
        self._atr_cache[pair] = float(atr)

        entry_price = trade.open_rate
        stop_distance = self.atr_multiplier * atr

        # Calculate stop price
        stop_price = entry_price - stop_distance

        # Progressive stop tightening with profit
        if current_profit > 0.030:
            # At 3%+ profit: stop just below entry (lock in profit)
            stop_price = max(entry_price * 0.995, stop_price)
        elif current_profit > 0.015:
            # At 1.5%+ profit: allow 0.5% below entry
            stop_price = max(entry_price * 0.998, stop_price)
        elif current_profit > 0.008:
            # At 0.8%+ profit: use half ATR distance
            stop_price = entry_price - (stop_distance * 0.5)
        # Below that: full ATR distance

        stop_pct = (stop_price / entry_price) - 1

        # Never exceed configured hard stoploss
        return max(stop_pct, -abs(self.stoploss))

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        """
        Trade-specific exit logic:
        1. Hard time exit (240 min LEA/Hybrid) — no conditions
        2. Partial take-profit signal at configured profit level
        3. Hard stoploss guard at -3%
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None

        last = dataframe.iloc[-1]
        tag = (trade.enter_tag or "").lower()
        trade_age = current_time - trade.open_date_utc

        # =========================================================
        # 1. HARD TIME EXIT — fires first, no conditions
        # =========================================================
        if "lea" in tag:
            if trade_age >= timedelta(minutes=self.lea_max_hold_minutes):
                return "time_exit_horizon"

        if "hybrid" in tag or "finagent" in tag:
            if trade_age >= timedelta(minutes=self.hybrid_max_hold_minutes):
                return "time_exit_horizon"

        # =========================================================
        # 2. PIVOT TAKE-PROFIT — removed (pivot levels below entry, causing losses)
        # =========================================================

        # =========================================================
        # 2. PARTIAL TAKE-PROFIT SIGNAL
        # =========================================================
        if self.partial_tp_enabled and current_profit >= self.partial_tp_profit:
            return "partial_tp_early"

        # =========================================================
        # 3. HARD STOPLOSS GUARD
        # =========================================================
        if current_profit < -0.03:
            return "hard_stoploss_guard"

        return None

    # =====================================================================
    # ENTRY CONFIRMATION
    # =====================================================================

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
        """Final trade confirmation using the actual selected entry_tag."""
        def _reject(reason: str, context_val: str = "unknown", strategy_val: str = "unknown") -> bool:
            self.log_event(
                "entry_rejected",
                {
                    "pair": pair,
                    "entry_tag": entry_tag or "",
                    "context": context_val,
                    "strategy": strategy_val,
                    "reason": reason,
                    "pred_col": pred_col if "pred_col" in locals() else None,
                    "pred_value": self._safe_float(pred_value) if "pred_value" in locals() else None,
                    "quantile": self._safe_float(quantile) if "quantile" in locals() else None,
                    "volume": self._safe_float(volume) if "volume" in locals() else None,
                    "avg_volume_20": self._safe_float(avg_volume) if "avg_volume" in locals() else None,
                    "close": self._safe_float(close) if "close" in locals() else None,
                    "atr": self._safe_float(atr) if "atr" in locals() else None,
                },
            )
            return False

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return _reject("no_dataframe")

        last_candle = dataframe.iloc[-1]
        pred_col = self._get_prediction_column(dataframe)
        if pred_col is None:
            return _reject("missing_prediction_column")

        tag = (entry_tag or "").lower()
        pred_value = last_candle.get(pred_col, np.nan)
        quantile = last_candle.get("pred_quantile", np.nan)
        volume = last_candle.get("volume", np.nan)
        avg_volume = dataframe["volume"].rolling(20).mean().iloc[-1]
        close = last_candle.get("close", np.nan)
        ema_50 = last_candle.get("ema_50", np.nan)
        atr = last_candle.get("atr", np.nan)
        pivot = last_candle.get("pivot", np.nan)
        r1 = last_candle.get("r1", np.nan)
        context = "unknown"
        if "_ctx_" in tag:
            context = tag.split("_ctx_", 1)[1]

        if pd.isna(pred_value) or pd.isna(volume) or pd.isna(avg_volume):
            return _reject("nan_required_field", context_val=context)

        # Strategy-specific confirmation
        if "lea" in tag:
            if pred_value <= self.lea_entry_threshold:
                return _reject("lea_pred_below_threshold", context_val=context, strategy_val="lea")
            if pd.notna(quantile) and quantile < self.ml_quantile_threshold:
                return _reject("lea_pred_below_quantile", context_val=context, strategy_val="lea")
            if pd.notna(close) and pd.notna(pivot) and close <= pivot:
                return _reject("lea_below_pivot", context_val=context, strategy_val="lea")
            if pd.notna(close) and pd.notna(r1) and close >= r1:
                return _reject("lea_at_resistance_r1", context_val=context, strategy_val="lea")
            selected_strategy = "lea"

        elif "hybrid" in tag:
            if pred_value <= self.hybrid_entry_threshold:
                return _reject("hybrid_pred_below_threshold", context_val=context, strategy_val="hybrid")
            if pd.notna(quantile) and quantile < self.ml_quantile_threshold:
                return _reject("hybrid_pred_below_quantile", context_val=context, strategy_val="hybrid")
            if pd.notna(close) and pd.notna(pivot) and close <= pivot:
                return _reject("hybrid_below_pivot", context_val=context, strategy_val="hybrid")
            selected_strategy = "hybrid"

        else:
            return _reject("unknown_entry_tag", context_val=context)

        # Common liquidity sanity check
        if volume < avg_volume * 0.3:
            return _reject(
                "liquidity_filter_failed",
                context_val=context,
                strategy_val=selected_strategy,
            )

        self.log_selection(
            pair=pair,
            context=context,
            strategy=selected_strategy,
            entry_tag=entry_tag or "",
        )
        self.log_event(
            "entry_confirmed",
            {
                "pair": pair,
                "entry_tag": entry_tag or "",
                "context": context,
                "strategy": selected_strategy,
                "pred_col": pred_col,
                "pred_value": self._safe_float(pred_value),
                "quantile": self._safe_float(quantile),
                "volume": self._safe_float(volume),
                "avg_volume_20": self._safe_float(avg_volume),
                "close": self._safe_float(close),
                "atr": self._safe_float(atr),
                "rate": self._safe_float(rate),
                "side": side,
            },
        )

        return True
