"""
FinAgent Strategy v2 - Integrated Version
Advanced Risk Management with ATR stops, quantile filtering, and pivot exits

Integrated features:
- Pivot-based entry filtering (bullish bias: close > pivot)
- Quantile-filtered ML entries (top 20% predictions only)
- ATR-based dynamic stop-loss (tightens with profit)
- Time-horizon exits (90 minutes max hold)
- Pivot R2 take-profit + partial TP signal
- Exit priority: time > pivot TP > partial TP > hard stop
"""
import logging
from datetime import timedelta, timezone
from functools import reduce
from collections import deque
import numpy as np
import pandas as pd
from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib
import hashlib

from freqtrade.strategy import IStrategy, Trade
from typing import Optional

# Import research data loader
try:
    from binance_research_backtest_loader import BinanceBacktestResearchLoader
    RESEARCH_LOADER_AVAILABLE = True
except ImportError:
    RESEARCH_LOADER_AVAILABLE = False
    logger_init = logging.getLogger(__name__)
    logger_init.warning("Research loader not available - running without Binance research data")

logger = logging.getLogger(__name__)


class RiskManager:
    """Advanced risk management using Kelly Criterion and portfolio heat"""

    def __init__(self):
        self.max_portfolio_risk = 0.06
        self.max_trade_risk = 0.015
        self.min_rr_ratio = 1.5
        self.base_position = 0.02

    def calculate_position(self, signal: float, confidence: float, regime: str, atr: float, price: float) -> dict:
        """Kelly Criterion position sizing"""
        win_prob = 0.45 + (signal * 0.25)
        win_prob = np.clip(win_prob * (0.8 + confidence * 0.4), 0.45, 0.70)
        rr_ratio = 1.5
        kelly = (win_prob * rr_ratio - (1 - win_prob)) / rr_ratio
        kelly = kelly * 0.25  # Conservative Kelly
        regime_mult = {
            'trending_up': 1.2, 'trending_down': 1.1,
            'ranging': 0.8, 'volatile': 0.6, 'uncertain': 0.5
        }.get(regime, 0.7)
        position_pct = self.base_position * kelly * regime_mult
        position_pct = np.clip(position_pct, 0.01, 0.05)
        stop_dist = np.clip((atr * 2.0) / price, 0.015, 0.04)
        target = np.clip(stop_dist * rr_ratio, stop_dist * 1.5, 0.10)
        if self.get_portfolio_heat() >= self.max_portfolio_risk:
            return {'size': 0, 'stop': -stop_dist, 'target': target}
        dd = self.get_drawdown()
        if dd > 0.15:
            position_pct *= 0.3
        elif dd > 0.10:
            position_pct *= 0.5
        elif dd > 0.05:
            position_pct *= 0.75
        return {'size': position_pct, 'stop': -stop_dist, 'target': target}

    def get_portfolio_heat(self) -> float:
        return 0.0

    def get_drawdown(self) -> float:
        return 0.0


class PatternMemory:
    """Pattern learning with confidence scoring"""

    def __init__(self, max_patterns=500):
        self.patterns = {}

    def hash_pattern(self, features: dict) -> str:
        feature_str = ''.join(f"{k}:{round(float(v), 4)}," for k, v in sorted(features.items()))
        return hashlib.md5(feature_str.encode()).hexdigest()[:16]

    def get_confidence(self, features: dict) -> float:
        h = self.hash_pattern(features)
        if h not in self.patterns:
            return 1.0
        outcomes = self.patterns.get(h, {}).get('outcomes', [])
        if not outcomes:
            return 1.0
        win_rate = sum(1 for o in outcomes if o > 0) / len(outcomes)
        return 0.5 + (win_rate * 1.0)


class MarketRegimeDetector:
    """Market regime classification"""

    def detect_regime(self, df: DataFrame) -> str:
        if len(df) < 50:
            return 'uncertain'
        recent = df.tail(50)
        adx = ta.ADX(recent, timeperiod=14)
        atr = ta.ATR(recent, timeperiod=14)
        atr_pct = (atr.iloc[-1] / recent['close'].iloc[-1] * 100) if len(atr) > 0 else 2
        ema_20 = ta.EMA(recent, timeperiod=20)
        ema_50 = ta.EMA(recent, timeperiod=50)
        trend_diff = (ema_20.iloc[-1] - ema_50.iloc[-1]) / ema_50.iloc[-1] if len(ema_20) > 0 else 0
        adx_val = adx.iloc[-1] if len(adx) > 0 else 20
        if adx_val > 25:
            return 'trending_up' if trend_diff > 0.02 else 'trending_down'
        if atr_pct > 3.0:
            return 'volatile'
        if (recent['high'].max() - recent['low'].min()) / recent['close'].mean() < 0.02:
            return 'ranging'
        return 'uncertain'


class NormalizedIndicators:
    """Normalized indicator signals"""

    def process(self, df: DataFrame) -> dict:
        signals = {}
        if len(df) < 30:
            return {k: 0.0 for k in ['rsi', 'macd', 'bb', 'volume', 'trend']}
        rsi = ta.RSI(df, timeperiod=14)
        signals['rsi'] = (rsi.iloc[-1] - 50) / 50 if len(rsi) > 0 else 0
        macd_data = ta.MACD(df)
        if len(macd_data) > 0:
            hist = macd_data['macdhist']
            hist_mean = hist.rolling(50).mean().iloc[-1]
            hist_std = hist.rolling(50).std().iloc[-1]
            signals['macd'] = (hist.iloc[-1] - hist_mean) / (hist_std + 1e-10) if hist_std > 0 else 0
        else:
            signals['macd'] = 0.0
        bb = qtpylib.bollinger_bands(df['close'], window=20, stds=2)
        if len(bb) > 0:
            bb_width = bb['upper'].iloc[-1] - bb['lower'].iloc[-1]
            signals['bb'] = (df['close'].iloc[-1] - bb['mid'].iloc[-1]) / (bb_width / 2 + 1e-10) if bb_width > 0 else 0
        else:
            signals['bb'] = 0.0
        vol_ma = df['volume'].rolling(20).mean()
        signals['volume'] = np.tanh((df['volume'].iloc[-1] / (vol_ma.iloc[-1] + 1e-10) - 1) * 2) if len(vol_ma) > 0 else 0
        ema_20 = ta.EMA(df, timeperiod=20)
        ema_50 = ta.EMA(df, timeperiod=50)
        signals['trend'] = np.clip((ema_20.iloc[-1] - ema_50.iloc[-1]) / (ema_50.iloc[-1] + 1e-10) * 10, -1, 1) if len(ema_20) > 0 else 0
        return {k: np.clip(v, -1, 1) for k, v in signals.items()}


def _apply_freqai_fallback(dataframe: DataFrame) -> DataFrame:
    """Fail-closed fallback when FreqAI can't build live history."""
    dataframe["&-target"] = 0.0
    dataframe["do_predict"] = 0
    return dataframe


def _get_latest_signal_candle(dataframe: DataFrame) -> pd.Series:
    """Use latest completed candle for trade decisions."""
    if len(dataframe) == 0:
        return pd.Series(dtype=float)
    if len(dataframe) == 1:
        return dataframe.iloc[-1]
    return dataframe.iloc[-2]


class FinAgentStrategy_v2_RiskManaged(IStrategy):
    """
    FinAgent v2 — integrated with pivot, quantile, ATR stop, and time exits.

    Entry requirements:
    - ML prediction > threshold AND top 20% quantile
    - close > pivot (bullish bias)
    - EMA50 > EMA200 (uptrend)
    - RSI < 70, MACD bullish
    - BTC trend > -5%

    Exit priority: time (90min) > pivot R2 > partial TP > hard stop
    """

    INTERFACE_VERSION = 3
    can_short = False

    timeframe = "5m"
    startup_candle_count = 200

    # =====================================================================
    # ML THRESHOLDS & QUANTILES
    # =====================================================================
    ml_entry_threshold = 0.01
    ml_quantile_threshold = 0.80  # Top 20% only
    strong_signal_multiplier = 1.5
    trend_floor_ratio = 0.995

    # =====================================================================
    # ATR STOP-LOSS
    # =====================================================================
    atr_period = 14
    atr_multiplier = 1.5

    # =====================================================================
    # TIME & EXIT
    # =====================================================================
    max_hold_minutes = 90
    partial_tp_enabled = True
    partial_tp_profit = 0.01
    hard_stop = -0.03

    # =====================================================================
    # ROI & STOPLOSS
    # =====================================================================
    minimal_roi = {
        "0": 0.018,
        "30": 0.010,
        "60": 0.008,
        "120": 0.005,
    }

    stoploss = -0.20
    use_custom_stoploss = True
    trailing_stop = False

    process_only_new_candles = True
    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False
    }
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    def __init__(self, config: dict):
        super().__init__(config)
        self.risk_mgr = RiskManager()
        self.pattern_mem = PatternMemory()
        self.regime = MarketRegimeDetector()
        self.indicators = NormalizedIndicators()
        self.custom_info = {}
        self._atr_cache: dict[str, float] = {}
        self.enable_live_research_features = False
        self.research_loader = None
        self.research_data_cache = {}

        if RESEARCH_LOADER_AVAILABLE:
            try:
                self.research_loader = BinanceBacktestResearchLoader()
                logger.info("Research loader initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize research loader: {e}")

    @property
    def plot_config(self):
        return {
            "main_plot": {"ema_50": {"color": "blue"}, "ema_200": {"color": "orange"}},
            "subplots": {
                "RSI": {"rsi": {"color": "red"}},
                "MACD": {"macd": {"color": "blue"}, "macdsignal": {"color": "orange"}},
                "AI": {"&-target": {"color": "green"}}
            }
        }

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int, metadata: dict, **kwargs) -> DataFrame:
        """Create stationary features — MUST MATCH LeaFreqAI."""
        dataframe["%ret_1"] = dataframe["close"].pct_change(1)
        dataframe["%ret_3"] = dataframe["close"].pct_change(3)
        dataframe["%ret_12"] = dataframe["close"].pct_change(12)
        dataframe["atr14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["%atr14_rel"] = dataframe["atr14"] / dataframe["close"]
        dataframe["%rng_24"] = (
            dataframe["high"].rolling(24).max() - dataframe["low"].rolling(24).min()
        ) / dataframe["close"]
        returns = dataframe["close"].pct_change()
        returns_mean_48 = returns.rolling(48).mean()
        returns_std_48 = returns.rolling(48).std().replace(0, np.nan)
        dataframe["%z_48"] = (
            (returns - returns_mean_48) / returns_std_48
        ).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        volume_mean_48 = dataframe["volume"].rolling(48).mean()
        volume_std_48 = dataframe["volume"].rolling(48).std().replace(0, np.nan)
        dataframe["%vol_z_48"] = (
            (dataframe["volume"] - volume_mean_48) / volume_std_48
        ).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe["%bb_width"] = (dataframe["bb_upperband"] - dataframe["bb_lowerband"]) / dataframe["bb_middleband"]
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        return self.feature_engineering_expand_all(dataframe, period=1, metadata=metadata)

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """Market regime features — MUST MATCH LeaFreqAI."""
        if metadata.get("pair") != "BTC/USDT" and self.dp:
            btc_dataframe = self.dp.get_pair_dataframe(pair="BTC/USDT", timeframe=self.timeframe)
            if not btc_dataframe.empty and len(btc_dataframe) > 50:
                btc_ema = ta.EMA(btc_dataframe["close"], timeperiod=50)
                btc_trend = (btc_dataframe["close"] - btc_ema) / btc_ema
                btc_vol = btc_dataframe["close"].pct_change().rolling(48).std()
                dataframe["%btc_trend"] = btc_trend.reindex(dataframe.index, method='ffill')
                dataframe["%market_vol"] = btc_vol.reindex(dataframe.index, method='ffill')
            else:
                dataframe["%btc_trend"] = 0.0
                dataframe["%market_vol"] = dataframe["close"].pct_change().rolling(48).std()
        else:
            dataframe["%btc_trend"] = 0.0
            dataframe["%market_vol"] = dataframe["close"].pct_change().rolling(48).std()
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        dataframe["&-target"] = dataframe["close"].shift(-12).pct_change(periods=12, fill_method=None)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """FreqAI predictions + indicators + pivot points + quantile."""
        try:
            dataframe = self.freqai.start(dataframe, metadata, self)
        except Exception as exc:
            pair = metadata.get("pair", "UNKNOWN")
            logger.warning(
                f"[{pair}] FreqAI prediction failed ({exc.__class__.__name__}: {exc}). "
                "Using fail-closed fallback frame."
            )
            dataframe = _apply_freqai_fallback(dataframe)

        # Recompute indicators FreqAI doesn't preserve
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr14"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_middleband"] = bollinger["mid"]

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

        # === Confluence score for position sizing ===
        rsi = ta.RSI(dataframe, timeperiod=14)
        macd_data = ta.MACD(dataframe)
        bb = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        ema_20 = ta.EMA(dataframe, timeperiod=20)
        ema_50 = ta.EMA(dataframe, timeperiod=50)

        rsi_signal = (rsi - 50) / 50
        hist = macd_data['macdhist']
        hist_mean = hist.rolling(50).mean()
        hist_std = hist.rolling(50).std().replace(0, np.nan)
        macd_signal = (hist - hist_mean) / hist_std
        macd_signal = macd_signal.fillna(pd.Series(np.where(hist > 0, 1.0, -1.0), index=macd_signal.index))
        macd_signal = np.clip(macd_signal, -1, 1)

        vol_ma = dataframe['volume'].rolling(20).mean()
        vol_ratio = dataframe['volume'] / vol_ma
        volume_signal = np.clip((vol_ratio - 1) * 0.5, -1, 1)

        bb_width = bb['upper'] - bb['lower']
        bb_width = bb_width.replace(0, np.nan)
        bb_mid = bb['mid'].iloc[:, 0] if isinstance(bb['mid'], pd.DataFrame) else bb['mid']
        bb_position = (dataframe['close'] - bb_mid) / (bb_width / 2)
        bb_signal = np.clip(bb_position, -1, 1)

        trend_diff = (ema_20 - ema_50) / ema_50
        trend_signal = np.clip(trend_diff * 50, -1, 1)

        signals_df = pd.DataFrame({
            'rsi': rsi_signal,
            'macd': macd_signal,
            'volume': volume_signal,
            'bb': bb_signal,
            'trend': trend_signal
        })
        dataframe['confluence_score'] = (signals_df > 0.2).sum(axis=1) / 5.0
        dataframe['confluence_score'] = dataframe['confluence_score'].fillna(0)

        return dataframe

    def _quantile_filter(self, dataframe: DataFrame, pred_col: str) -> pd.Series:
        """Return mask for top X% predictions (ml_quantile_threshold)."""
        if "pred_quantile" in dataframe.columns:
            return dataframe["pred_quantile"] >= self.ml_quantile_threshold
        return dataframe[pred_col] >= dataframe[pred_col].quantile(self.ml_quantile_threshold)

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        FinAgent entry with pivot + quantile + supply/demand zone filters.

        Requirements:
        1. ML prediction > threshold AND top quantile
        2. close > pivot (bullish bias)
        3. EMA50 > EMA200 (uptrend) OR strong ML signal
        4. RSI < 70
        5. MACD bullish
        6. BTC trend > -5%
        7. close <= demand_zone * 1.02 (near recent support)
        8. close < supply_zone * 0.98 (away from recent resistance)
        """
        if "&-target" not in dataframe.columns:
            dataframe["enter_long"] = 0
            return dataframe

        if len(dataframe) < 20:
            dataframe["enter_long"] = 0
            return dataframe

        pred_col = "&-target"

        ml_signal = dataframe[pred_col] > self.ml_entry_threshold
        strong_ml_signal = dataframe[pred_col] > (self.ml_entry_threshold * self.strong_signal_multiplier)

        # Pivot filter: close > pivot (bullish bias)
        pivot_ok = dataframe["close"] > dataframe["pivot"]

        # Trend: EMA50 > EMA200 OR strong ML
        trend_ok = dataframe["ema_50"] > dataframe["ema_200"]
        trend_filter_ok = trend_ok | strong_ml_signal

        # RSI
        rsi_ok = dataframe["rsi"] < 70

        # MACD bullish
        macd_ok = dataframe["macd"] > dataframe["macdsignal"]

        # BTC trend
        btc_ok = dataframe["%btc_trend"] > -0.05 if "%btc_trend" in dataframe.columns else pd.Series(True, index=dataframe.index)

        # Volume
        volume_ok = dataframe["volume"] > dataframe["vol_mean_20"]

        entry_signal = (
            ml_signal
            & self._quantile_filter(dataframe, pred_col)
            & pivot_ok
            & trend_filter_ok
            & rsi_ok
            & macd_ok
            & btc_ok
            # === Supply & Demand Zone Filters ===
            & (dataframe["close"] <= dataframe["demand_zone"] * 1.02)  # Near demand zone
            & (dataframe["close"] < dataframe["supply_zone"] * 0.98)   # Away from supply zone
        )

        dataframe["enter_long"] = 0
        dataframe.loc[entry_signal, "enter_long"] = 1

        # Align live decision to latest completed candle
        signal_candle = _get_latest_signal_candle(dataframe)
        signal_idx = signal_candle.name
        live_idx = dataframe.index[-1]
        if signal_idx is not None and live_idx is not None:
            dataframe.at[live_idx, "enter_long"] = int(bool(entry_signal.loc[signal_idx]))

        logger.debug(
            f"[{metadata['pair']}] FinAgent entry signals: "
            f"{int(entry_signal.sum())}/{len(dataframe)}"
        )
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Keep exit neutral; all exits via custom_exit() and custom_stoploss()."""
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
        Stop = entry - (ATR × multiplier), tightens with profit.
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

        # Progressive tightening with profit
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
    ) -> Optional[str]:
        """
        FinAgent exit logic — priority order:
        1. Time exit (90 min) — no conditions, fires first
        2. Pivot R2 take-profit
        3. Partial TP signal at 1% profit
        4. Hard stop at -3%
        """
        # Timezone-safe arithmetic
        open_date = trade.open_date_utc
        if open_date.tzinfo is None:
            open_date = open_date.replace(tzinfo=timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        trade_age = current_time - open_date

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None

        last = dataframe.iloc[-1]

        # 1. HARD TIME EXIT — fires first, no conditions
        if trade_age >= timedelta(minutes=self.max_hold_minutes):
            logger.info(
                f"[{pair}] FinAgent exit=time_exit_horizon "
                f"age_min={trade_age.total_seconds() / 60:.1f} "
                f"profit={current_profit:.4f}"
            )
            return "time_exit_horizon"

        # 2. PIVOT R2 TAKE-PROFIT
        r2 = last.get("r2")
        if pd.notna(r2) and current_rate >= r2:
            logger.info(
                f"[{pair}] FinAgent exit=pivot_r2_take_profit "
                f"rate={current_rate:.8f} r2={r2:.8f} profit={current_profit:.4f}"
            )
            return "pivot_r2_take_profit"

        # 3. PARTIAL TAKE-PROFIT SIGNAL
        if self.partial_tp_enabled and current_profit >= self.partial_tp_profit:
            logger.info(
                f"[{pair}] FinAgent exit=partial_tp_early "
                f"profit={current_profit:.4f}"
            )
            return "partial_tp_early"

        # 4. HARD STOPLOSS GUARD
        if current_profit <= self.hard_stop:
            logger.info(
                f"[{pair}] FinAgent exit=hard_stoploss_guard "
                f"profit={current_profit:.4f}"
            )
            return "hard_stoploss_guard"

        return None

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
        """Dynamic position sizing via risk manager + confluence score."""
        if not self.wallets:
            return min_stake

        result = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        df = result[0] if isinstance(result, tuple) else result

        if "&-target" not in df.columns:
            return min_stake

        signal_candle = _get_latest_signal_candle(df)
        signal = abs(signal_candle['&-target'])

        # Count confluence filters
        confluence_count = 0
        atr_pct = (signal_candle['atr14'] / signal_candle['close']) * 100
        if atr_pct < 3.0:
            confluence_count += 1
        if signal_candle["close"] > signal_candle["ema_50"]:
            confluence_count += 1
        if signal_candle["rsi"] < 70:
            confluence_count += 1
        if signal_candle["volume"] > df["volume"].rolling(20).mean().iloc[-2]:
            confluence_count += 1
        if signal_candle["macdhist"] > 0:
            confluence_count += 1
        if signal_candle["close"] < signal_candle["bb_middleband"]:
            confluence_count += 1

        confluence_multiplier = 0.6 + (confluence_count / 6 * 0.4)

        confidence = self.pattern_mem.get_confidence({'signal': signal, 'confluence': confluence_count})
        regime = self.regime.detect_regime(df)
        atr = ta.ATR(df, timeperiod=14).iloc[-2]

        risk_metrics = self.risk_mgr.calculate_position(
            signal, confidence, regime, atr, signal_candle['close']
        )

        if risk_metrics['size'] == 0:
            return 0

        risk_metrics['size'] = risk_metrics['size'] * confluence_multiplier
        self.custom_info[pair] = risk_metrics

        portfolio_value = self.wallets.get_total_stake_amount()
        if portfolio_value <= 0:
            return min_stake

        stake = portfolio_value * risk_metrics['size']
        return max(min_stake, min(stake, max_stake))

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
        """Final confirmation: re-check pivot + quantile + regime."""
        result = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        df = result[0] if isinstance(result, tuple) else result
        if df.empty or "&-target" not in df.columns:
            return False

        current_candle = df.iloc[-1]
        signal_candle = _get_latest_signal_candle(df)

        atr_pct = (signal_candle["atr14"] / signal_candle["close"]) * 100
        target_value = float(signal_candle["&-target"])
        strong_ml_signal = target_value > (self.ml_entry_threshold * self.strong_signal_multiplier)

        # ATR regime check
        if atr_pct >= 3.0:
            logger.debug(f"[{pair}] FinAgent confirm: atr_pct {atr_pct:.3f} >= 3.0")
            return False

        # do_predict check
        if "do_predict" in df.columns and int(signal_candle["do_predict"]) != 1:
            logger.debug(f"[{pair}] FinAgent confirm: do_predict != 1")
            return False

        # Pivot filter: close > pivot
        close = float(signal_candle["close"])
        pivot = float(signal_candle["pivot"])
        if close <= pivot:
            logger.debug(f"[{pair}] FinAgent confirm: close {close:.8f} <= pivot {pivot:.8f}")
            return False

        # Quantile check
        quantile = signal_candle.get("pred_quantile", 0.0)
        if pd.notna(quantile) and quantile < self.ml_quantile_threshold:
            logger.debug(f"[{pair}] FinAgent confirm: quantile {quantile:.3f} < {self.ml_quantile_threshold}")
            return False

        # Already passed populate_entry_trend signal
        signal_enter = bool(current_candle.get("enter_long", 0) == 1)
        if signal_enter:
            return True

        if strong_ml_signal:
            return True

        logger.debug(f"[{pair}] FinAgent confirm: weak_signal target={target_value:.6f}")
        return False
