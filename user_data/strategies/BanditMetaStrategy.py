"""
Contextual Bandit Meta-Strategy
Selects between LeaFreqAI and HybridAI strategies based on market context

This is a meta-strategy that:
1. Observes market context (volatility, trend, time)
2. Selects the best strategy for that context (epsilon-greedy)
3. Uses the selected strategy's entry/exit logic
4. Logs decisions for offline learning

Run meta_learner.py daily to update Q-values from trade outcomes.
"""
import json
import logging
import numpy as np
from pathlib import Path
from functools import reduce
from datetime import datetime
from typing import Optional

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)


class BanditMetaStrategy(IStrategy):
    """
    Contextual bandit strategy selector

    Chooses between two strategies based on context:
    - LeaFreqAIStrategy: Conservative (tight stops, quick exits)
    - HybridAIStrategy: Aggressive (wider stops, patient exits)

    Context dimensions:
    - Market volatility (low/med/high)
    - Pair trend (down/flat/up)
    - Time of day (morning/day/evening)

    Selection: Epsilon-greedy (90% exploit best Q-value, 10% explore)
    """

    # Strategy metadata
    INTERFACE_VERSION = 3
    can_short = False

    # Timeframe (matches both sub-strategies)
    timeframe = "5m"

    # Startup candles
    startup_candle_count = 200

    # Risk parameters (will be overridden by selected strategy logic)
    # Using LEA's conservative defaults as base
    minimal_roi = {
        "0": 0.015,
        "30": 0.01,
        "60": 0.008,
        "120": 0.005
    }

    stoploss = -0.05
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.01

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

    def __init__(self, config: dict):
        super().__init__(config)

        # Load bandit selector
        self.selector_path = Path("user_data/bandit_selector.json")
        self.load_selector()

        # Track strategy selection per pair (for exit logic)
        self.pair_strategy_map = {}

        logger.info("BanditMetaStrategy initialized")
        logger.info(f"Selector loaded: {len(self.selector.get('contexts', {}))} contexts")

    def load_selector(self):
        """Load bandit selection table or initialize with defaults"""
        if self.selector_path.exists():
            with open(self.selector_path) as f:
                self.selector = json.load(f)
                logger.info(f"Loaded selector from {self.selector_path}")
        else:
            # Initialize with uniform priors (no knowledge yet)
            self.selector = {
                "contexts": {},
                "epsilon": 0.1,  # 10% exploration
                "alpha": 0.1,    # Learning rate (not used in strategy, only meta_learner)
                "last_updated": None,
                "total_trades_processed": 0
            }
            logger.warning(f"No selector found at {self.selector_path}, initialized with defaults")
            logger.warning("Run trades and meta_learner.py to build Q-values")

    def get_context(self, dataframe: DataFrame, pair: str) -> str:
        """
        Extract current market context

        Returns context string like: "vol_low_trend_up_hour_day"
        """
        if len(dataframe) < 50:
            return "vol_med_trend_flat_hour_day"  # Default for insufficient data

        last = dataframe.iloc[-1]

        # 1. Market volatility (from BTC correlation feature)
        if "%market_vol" in dataframe.columns:
            market_vol = last["%market_vol"]
            if pd.notna(market_vol):
                if market_vol < 0.02:
                    vol_regime = "low"
                elif market_vol > 0.05:
                    vol_regime = "high"
                else:
                    vol_regime = "med"
            else:
                vol_regime = "med"
        else:
            # Fallback: use pair's own volatility
            returns = dataframe["close"].pct_change()
            vol = returns.rolling(48).std().iloc[-1]
            if pd.notna(vol):
                vol_regime = "low" if vol < 0.02 else ("high" if vol > 0.05 else "med")
            else:
                vol_regime = "med"

        # 2. Pair trend strength
        if "ema_50" in dataframe.columns:
            ema50 = last["ema_50"]
            close = last["close"]
            if pd.notna(ema50) and ema50 > 0:
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
            if hasattr(last.name, 'hour'):
                hour = last.name.hour
            else:
                hour = datetime.now().hour

            if hour < 8:
                time_regime = "morning"
            elif hour < 16:
                time_regime = "day"
            else:
                time_regime = "evening"
        except Exception:
            time_regime = "day"

        # Construct context key
        context = f"vol_{vol_regime}_trend_{trend_regime}_hour_{time_regime}"
        return context

    def select_strategy(self, context: str, pair: str) -> str:
        """
        Epsilon-greedy strategy selection

        Returns:
            "lea" or "hybrid"
        """
        epsilon = self.selector.get("epsilon", 0.1)

        # Exploration: random choice (10% of time)
        if np.random.random() < epsilon:
            selected = np.random.choice(["lea", "hybrid"])
            logger.debug(f"[{pair}] EXPLORE: Selected {selected} (ε={epsilon:.2f})")
            return selected

        # Exploitation: choose best Q-value
        if context not in self.selector["contexts"]:
            # Unknown context: default to conservative LEA
            logger.debug(f"[{pair}] Unknown context '{context}', defaulting to LEA")
            return "lea"

        ctx_data = self.selector["contexts"][context]

        # Get Q-values for each strategy
        lea_q = ctx_data.get("LeaFreqAIStrategy", {}).get("q_value", 0.0)
        hybrid_q = ctx_data.get("HybridAIStrategy", {}).get("q_value", 0.0)

        # Select best
        if lea_q >= hybrid_q:
            selected = "lea"
            logger.debug(f"[{pair}] EXPLOIT: LEA (Q={lea_q:.4f}) > Hybrid (Q={hybrid_q:.4f})")
        else:
            selected = "hybrid"
            logger.debug(f"[{pair}] EXPLOIT: Hybrid (Q={hybrid_q:.4f}) > LEA (Q={lea_q:.4f})")

        return selected

    def log_selection(self, pair: str, context: str, strategy: str):
        """
        Log strategy selection for offline learning

        Creates a JSONL file with selections that meta_learner.py can use
        to correlate with trade outcomes.
        """
        log_file = Path("user_data/bandit_selections.jsonl")

        entry = {
            "timestamp": datetime.now().isoformat(),
            "pair": pair,
            "context": context,
            "strategy": strategy
        }

        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to log selection: {e}")

    # ========================================================================
    # FREQAI FEATURE ENGINEERING (same as LeaFreqAIStrategy)
    # ========================================================================

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """Create stationary features for FreqAI"""
        # Price returns (stationary)
        dataframe[f"%ret_1"] = dataframe["close"].pct_change(1)
        dataframe[f"%ret_3"] = dataframe["close"].pct_change(3)
        dataframe[f"%ret_12"] = dataframe["close"].pct_change(12)

        # Volatility (ATR-based, relative)
        dataframe["atr14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe[f"%atr14_rel"] = dataframe["atr14"] / dataframe["close"]

        # Range (stationary)
        dataframe[f"%rng_24"] = (
            dataframe["high"].rolling(24).max() - dataframe["low"].rolling(24).min()
        ) / dataframe["close"]

        # Z-score (mean reversion)
        returns = dataframe["close"].pct_change()
        dataframe[f"%z_48"] = (returns - returns.rolling(48).mean()) / returns.rolling(48).std()

        # Volume indicators
        dataframe[f"%vol_z_48"] = (
            (dataframe["volume"] - dataframe["volume"].rolling(48).mean())
            / dataframe["volume"].rolling(48).std()
        )

        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # Bollinger Bands
        from technical import qtpylib
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["%bb_width"] = (
            (dataframe["bb_upperband"] - dataframe["bb_lowerband"]) / dataframe["bb_middleband"]
        )

        # EMAs for trend
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        return dataframe

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """Basic feature engineering for main timeframe"""
        dataframe = self.feature_engineering_expand_all(dataframe, period=1, metadata=metadata)
        return dataframe

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """Market regime features (BTC correlation)"""
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
            # For BTC pair or if data unavailable
            dataframe["%btc_trend"] = 0.0
            dataframe["%market_vol"] = dataframe["close"].pct_change().rolling(48).std()

        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Define prediction target
        Target: Future return over next 12 candles (1 hour at 5m)
        """
        dataframe["&-target"] = dataframe["close"].shift(-12).pct_change(12)
        return dataframe

    # ========================================================================
    # INDICATOR POPULATION (FreqAI predictions)
    # ========================================================================

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate FreqAI predictions
        Both strategies use the same predictions, they differ only in entry/exit logic
        """
        # Run FreqAI
        dataframe = self.freqai.start(dataframe, metadata, self)

        # Add indicators needed for entry/exit logic
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        # MACD (for Hybrid strategy)
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]

        return dataframe

    # ========================================================================
    # ENTRY LOGIC (selects strategy, then applies its logic)
    # ========================================================================

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Select strategy based on context, then apply its entry logic
        """
        pair = metadata["pair"]

        # Check if predictions available
        if "&-target" not in dataframe.columns:
            logger.warning(f"[{pair}] No FreqAI predictions, no entries")
            dataframe["enter_long"] = 0
            return dataframe

        # Extract context
        context = self.get_context(dataframe, pair)

        # Select strategy (epsilon-greedy)
        selected = self.select_strategy(context, pair)

        # Store selection for exit logic
        self.pair_strategy_map[pair] = selected

        # Log selection
        self.log_selection(pair, context, selected)

        # Apply selected strategy's entry logic
        if selected == "lea":
            dataframe = self._populate_entry_lea(dataframe, metadata, context)
        else:
            dataframe = self._populate_entry_hybrid(dataframe, metadata, context)

        return dataframe

    def _populate_entry_lea(
        self, dataframe: DataFrame, metadata: dict, context: str
    ) -> DataFrame:
        """
        LEA strategy entry logic
        Conservative: tight filters, high confidence threshold
        """
        conditions = []

        # ML prediction must be positive (0.5% threshold)
        conditions.append(dataframe["&-target"] > 0.005)

        # DI filter (if available)
        if "do_predict" in dataframe.columns:
            conditions.append(dataframe["do_predict"] == 1)

        # Trend: price above 50 EMA
        conditions.append(dataframe["close"] > dataframe["ema_50"])

        # RSI: avoid overbought
        conditions.append(dataframe["rsi"] < 70)

        # Volume: above average
        conditions.append(dataframe["volume"] > dataframe["volume"].rolling(20).mean())

        # Combine
        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "enter_long"] = 1

        # Tag with strategy and context for tracking
        dataframe["enter_tag"] = f"lea_bandit_ctx_{context}"

        return dataframe

    def _populate_entry_hybrid(
        self, dataframe: DataFrame, metadata: dict, context: str
    ) -> DataFrame:
        """
        Hybrid strategy entry logic
        Aggressive: more lenient filters, lower threshold
        """
        conditions = []

        # ML prediction (lower threshold: 0.1%)
        conditions.append(dataframe["&-target"] > 0.001)

        # Trend: EMA 50 above EMA 200 (broader uptrend)
        conditions.append(dataframe["ema_50"] > dataframe["ema_200"])

        # RSI: not overbought
        conditions.append(dataframe["rsi"] < 70)

        # MACD: bullish
        conditions.append(dataframe["macd"] > dataframe["macdsignal"])

        # BTC trend filter (if available)
        if "%btc_trend" in dataframe.columns:
            conditions.append(dataframe["%btc_trend"] > -0.05)

        # Volume
        conditions.append(dataframe["volume"] > 0)

        # Combine
        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "enter_long"] = 1

        # Tag
        dataframe["enter_tag"] = f"hybrid_bandit_ctx_{context}"

        return dataframe

    # ========================================================================
    # EXIT LOGIC (uses same strategy as entry)
    # ========================================================================

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit logic based on which strategy was used for entry
        """
        pair = metadata["pair"]

        # Check predictions
        if "&-target" not in dataframe.columns:
            dataframe["exit_long"] = 0
            return dataframe

        # Use same strategy as entry (stored in map)
        selected = self.pair_strategy_map.get(pair, "lea")

        if selected == "lea":
            dataframe = self._populate_exit_lea(dataframe, metadata)
        else:
            dataframe = self._populate_exit_hybrid(dataframe, metadata)

        return dataframe

    def _populate_exit_lea(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        LEA exit: only on strong negative prediction
        (ROI and stoploss handle most exits)
        """
        dataframe.loc[dataframe["&-target"] < -0.004, "exit_long"] = 1
        return dataframe

    def _populate_exit_hybrid(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Hybrid exit: negative prediction OR technical signals
        """
        # AI exit
        ai_exit = dataframe["&-target"] < -0.001

        # MACD bearish
        macd_exit = dataframe["macd"] < dataframe["macdsignal"]

        # RSI overbought
        rsi_exit = dataframe["rsi"] > 80

        # Combine (OR logic)
        dataframe.loc[ai_exit | macd_exit | rsi_exit, "exit_long"] = 1

        return dataframe

    # ========================================================================
    # TRADE CONFIRMATION (uses selected strategy's logic)
    # ========================================================================

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
        **kwargs
    ) -> bool:
        """Final trade confirmation"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]

        # Check predictions
        if "&-target" not in dataframe.columns:
            return False

        # Determine which strategy was selected (from entry_tag)
        if "lea" in entry_tag.lower():
            # LEA confirmation: stricter
            if last_candle["&-target"] <= 0.005:
                return False

            # Confirm uptrend
            if last_candle["close"] <= last_candle["ema_50"]:
                return False

        else:
            # Hybrid confirmation: more lenient
            if last_candle["&-target"] <= 0.0005:
                return False

        # Volume check (both strategies)
        avg_volume = dataframe["volume"].rolling(20).mean().iloc[-1]
        if last_candle["volume"] < avg_volume * 0.3:
            return False

        return True
