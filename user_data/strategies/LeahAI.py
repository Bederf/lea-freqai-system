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

import json
import logging
import os
from datetime import datetime, timedelta
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


class LeahAI(IStrategy):
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

    use_exit_signal = True   # True — required for custom_exit (time exit) to fire (v4.3 fix)
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

    # =========================================================================
    # v4.4 MODEL OVERRIDE
    # Load externally-trained 15-feature XGBClassifier (Experiment E validated).
    # Set "force_v44_model": true in config to enable.
    # =========================================================================
    _V4_4_FEATURES = [
        "vol_ratio_20", "vol_ratio_10", "vol_ratio_5", "vol_ratio_3",
        "vol_ma20", "vol_ma10",
        "%ret_1", "%ret_3", "candle_body", "hl_range",
        "lower_shadow", "upper_shadow", "mom_6", "atr14", "%atr14_rel",
    ]

    def _load_v44_model(self, pair: str):
        """Load v4.4 classifier and scaler for pair. Returns (model, scaler) or (None, None)."""
        try:
            import joblib
            from pathlib import Path
            # Normalize: BTC/USDT → BTC_USDT → BTC
            pf = pair.replace("/", "_")
            # Handle _USDT suffix: BTC_USDT → BTC
            if pf.endswith("_USDT"):
                pf_base = pf[:-5]  # remove _USDT
            else:
                pf_base = pf
            # Try: leah_v4_4_BTC_xgb_clf.pkl (no _USDT in filename)
            candidates = [
                Path(f"user_data/models/leah_v4_4_{pf_base}_xgb_clf.pkl"),
                Path(f"user_data/models/leah_v4_4_{pf}_xgb_clf.pkl"),
            ]
            model_path = next((p for p in candidates if p.exists()), None)
            if model_path is None:
                logger.warning(f"[{pair}] v4.4 model files not found — falling back to FreqAI")
                return None, None
            scaler_path = model_path.parent / f"{model_path.stem}_scaler.pkl"
            if not scaler_path.exists():
                logger.warning(f"[{pair}] v4.4 scaler not found — falling back to FreqAI")
                return None, None
            model = joblib.load(model_path)
            scaler = joblib.load(scaler_path)
            logger.warning(
                f"[{pair}] v4.4 model={model_path.name} scaler={scaler_path.name} "
                f"(15 features, AUC 0.6247 walk-forward)"
            )
            return model, scaler
        except Exception as exc:
            logger.warning(f"[{pair}] Failed to load v4.4 model: {exc}")
            return None, None

    def _apply_v44_prediction(self, dataframe: DataFrame, metadata: dict, model, scaler):
        """Overwrite &-target with v4.4 classifier probability.
        ALL 15 features are computed from raw OHLCV — FreqAI column names don't matter."""
        import numpy as np
        pair = metadata.get("pair", "?")

        # Work on a fresh copy to avoid mutating FreqAI's dataframe
        df = dataframe.copy()

        # ── Compute ALL 15 features from raw OHLCV ──────────────────────
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values
        op = df["open"].values

        # Returns
        pct1 = np.zeros(len(df))
        pct1[1:] = (close[1:] - close[:-1]) / close[:-1]
        df["%ret_1"] = pct1

        pct3 = np.zeros(len(df))
        pct3[3:] = (close[3:] - close[:-3]) / close[:-3]
        df["%ret_3"] = pct3

        # ATR
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        atr = np.zeros(len(df))
        atr[:14] = np.nan
        atr[14] = tr[:14].mean()
        for i in range(15, len(atr)):
            atr[i] = (atr[i-1] * 13 + tr[i]) / 14
        df["atr14"] = atr
        df["%atr14_rel"] = atr / close

        # Volume ratios
        for win in [3, 5, 10, 20]:
            vol_ma = np.zeros(len(df))
            for i in range(len(df)):
                start = max(0, i - win + 1)
                vol_ma[i] = np.mean(volume[start:i+1])
            df[f"vol_ratio_{win}"] = volume / np.where(vol_ma == 0, 1, vol_ma)

        # Volume MAs
        for win in [10, 20]:
            vol_ma = np.zeros(len(df))
            for i in range(len(df)):
                start = max(0, i - win + 1)
                vol_ma[i] = np.mean(volume[start:i+1])
            df[f"vol_ma{win}"] = vol_ma

        # HL range
        df["hl_range"] = (high - low) / close

        # Candle body
        df["candle_body"] = (close - op) / close

        # Upper/lower shadow
        max_co = np.maximum(close, op)
        min_co = np.minimum(close, op)
        df["upper_shadow"] = (high - max_co) / close
        df["lower_shadow"] = (min_co - low) / close

        # Momentum
        pct6 = np.zeros(len(df))
        pct6[6:] = (close[6:] - close[:-6]) / close[:-6]
        df["mom_6"] = pct6

        feat_df = df[self._V4_4_FEATURES].fillna(0)

        # Scale and predict
        X_s = scaler.transform(feat_df.values)
        probs = model.predict_proba(X_s)[:, 1]

        # Overwrite &-target with classifier probability
        dataframe["&-target"] = probs

        n_above = (probs >= 0.55).sum()
        logger.warning(
            f"[{pair}] v4.4 override — &-target mean={probs.mean():.4f}, "
            f"std={probs.std():.4f}, %>55={n_above}/{len(probs)}"
        )

    # =========================================================================

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

        # v4.4 external model (Experiment E validated classifier)
        # Only load if explicitly enabled — prevents accidental deployment
        self._v44_model = None
        self._v44_scaler = None
        self._v44_enabled = config.get("force_v44_model", False)
        if self._v44_enabled:
            logger.warning("force_v44_model=true — v4.4 classifier override ENABLED")

        # ── Paper Trading Monitor ─────────────────────────────────────
        # Tracks opportunity funnel and calibration buckets without slowing the bot
        self._pf_start_time = datetime.now()
        self._pf_candle_count = 0          # total candle evaluations
        self._pf_atr80_pass = 0            # passed g8 (ATR percentile)
        self._pf_prob_pass = 0             # passed g1 (probability gate)
        self._pf_entries = 0              # enter_long triggered
        self._pf_roi_exits = 0
        self._pf_time_exits = 0
        self._pf_sl_exits = 0
        self._pf_last_report = 0           # last candle count at report time
        # Calibration buckets: bucket -> {n, wins, pnl}
        self._cal_buckets = {
            "0.55-0.60": {"n":0,"wins":0,"pnl":0.0},
            "0.60-0.65": {"n":0,"wins":0,"pnl":0.0},
            "0.65-0.70": {"n":0,"wins":0,"pnl":0.0},
            ">0.70":    {"n":0,"wins":0,"pnl":0.0},
        }
        self._checkpoint_fired = {10:False, 25:False, 50:False}
            # Load per-pair models lazily in populate_indicators

        # Strategy metadata for decision audit trail — included in every snapshot
        self._snapshot_meta = {
            "strategy_name": "LeahAI",
            "strategy_version": "6.1",
            "identifier": config.get("freqai", {}).get("identifier", "unknown") if isinstance(config.get("freqai"), dict) else "unknown",
            "freqaimodel": config.get("freqai", {}).get("freqaimodel", "unknown") if isinstance(config.get("freqai"), dict) else "unknown",
            "ml_entry_probability": getattr(self, "ml_entry_probability", 0.55),
            "train_period_days": config.get("freqai", {}).get("train_period_days", "unknown") if isinstance(config.get("freqai"), dict) else "unknown",
            "v44_override": self._v44_enabled,
            "v44_model": "leah_v4_4_xgb_clf",
            "v44_features": "15-feature vol expansion schema",
        }

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
        # ATR percentile rank: rolling lookback of 2000 candles, min_periods 100
        # Computes what fraction of the lookback window had ATR < current ATR
        # raw=True: lambda receives numpy array, so use x[-1] not x.iloc[-1]
        dataframe["atr14_pct_rank"] = (
            dataframe["atr14"]
            .rolling(2000, min_periods=100)
            .apply(lambda x: (x < x[-1]).sum() / len(x), raw=True)
        )
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
    # FREQAI PREDICTION OVERRIDE
    # FreqAI 2026.4's XGBoostClassifier.predict() has a bug: it fits a
    # LabelEncoder on column names (['&-target']) instead of actual label values,
    # so classes_=[0] while the model predicts [0,1]. inverse_transform([1])
    # then raises ValueError. Override uses the model's own classes_ directly.
    #
    # NOTE: lea_v6 uses XGBoostRegressor (config: freqaimodel=XGBoostRegressor),
    # so BaseRegressorModel.predict() is the correct base. It returns a DataFrame
    # with column '&-target' containing the regression value — no probability cols.
    # =========================================================================

    def predict(self, unfiltered_df, dk, **kwargs):
        """
        Override for XGBoostRegressor (lea_v6). The base class (BaseRegressorModel.predict)
        returns pred_df with column '&-target': the raw regression value.

        FreqAI's data_drawer merges this back into the OHLCV dataframe, making
        '&-target' available in populate_entry_trend for threshold comparison.
        """
        from freqtrade.freqai.base_models.BaseRegressorModel import BaseRegressorModel

        pred_df, dk.do_predict = BaseRegressorModel.predict(self, unfiltered_df, dk, **kwargs)

        # pred_df columns: ['&-target'] — regression value, used directly in entry gate
        return pred_df, dk.do_predict

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
        pair = metadata.get("pair", "?")
        try:
            # Guard: if dataframe is None, return empty dataframe immediately
            if dataframe is None:
                logger.warning(f"[{pair}] populate_indicators received None — returning empty dataframe")
                df = pd.DataFrame()
                df["enter_long"] = 0
                return df
            dataframe = self.freqai.start(dataframe, metadata, self)
            # Guard: freqai.start can return None for some candles during training
            if dataframe is None:
                logger.warning(f'[{pair}] freqai.start returned None — applying fallback')
                dataframe = pd.DataFrame()
                dataframe['enter_long'] = 0
                return dataframe
        except Exception as exc:
            import traceback
            logger.warning(
                '[%s] FreqAI prediction failed (%%s: %%s). Fail-closed fallback applied.',
                pair, exc.__class__.__name__, exc
            )
            dataframe = _apply_freqai_fallback(dataframe)

        # ── v4.4 CLASSIFIER OVERRIDE ─────────────────────────────────────
        # Replace &-target with externally-trained 15-feature XGBClassifier
        # probabilities. Only active when force_v44_model=true in config.
        if self._v44_enabled:
            if not hasattr(self, '_v44_cache'):
                self._v44_cache = {}
            if pair not in self._v44_cache:
                self._v44_cache[pair] = self._load_v44_model(pair)
            model, scaler = self._v44_cache[pair]
            if model is not None and scaler is not None:
                self._apply_v44_prediction(dataframe, metadata, model, scaler)
            else:
                logger.warning(f"[{pair}] v4.4 model unavailable — using FreqAI &-target")

        # ── Debug log ────────────────────────────────────────────────────
        _cols = list(dataframe.columns)
        _has_1 = "1" in dataframe.columns
        _has_target = "&-target" in dataframe.columns
        _do_pred = dataframe["do_predict"].iloc[-1] if "do_predict" in dataframe.columns else -1
        _pred_val = dataframe["1"].iloc[-1] if _has_1 else float("nan")
        _target_mean = dataframe["&-target"].iloc[-1] if _has_target else float("nan")
        logger.warning(
            f"[{pair}] freqai.start done — col1={_has_1}, do_predict={_do_pred}, "
            f"pred={_pred_val:.4f}, target_mean={_target_mean:.4f}, cols={len(_cols)}, "
            f"v44={'ON' if self._v44_enabled else 'OFF'}"
        )

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
            if "1" in dataframe.columns:
                prob = dataframe["1"]  # col "1" = model P(vol expansion), not &-target (training label)
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
        # Guard: if dataframe is None (populate_indicators failed), fail safe
        if dataframe is None:
            logger.warning(f"[{metadata.get('pair', '?')}] populate_entry_trend received None — returning empty")
            dataframe = pd.DataFrame()
            dataframe["enter_long"] = 0
            return dataframe
            # =====================================================================
        # v4 entry conditions:
        #   1. P(vol expansion) > threshold
        #   2. %btc_trend >= 0.002 (BTC bull regime)
        #   3. close > ema_50 (pair in local uptrend)
        #   4. do_predict == 1 (FreqAI quality gate)
        #   5. volume > 0 (valid candle)
        #   6. atr14_pct_rank >= 80 (top 20% volatility)
        # =====================================================================

        # Guard: require %btc_trend column (created by feature_engineering_standard)
        if "%btc_trend" not in dataframe.columns:
            logger.warning(f"[{metadata['pair']}] No %btc_trend column -- no entries")
            dataframe["enter_long"] = 0
            return dataframe

        conditions = [
            # 1. Model regression value > threshold
            (dataframe["&-target"] > self.ml_entry_probability if "&-target" in dataframe.columns else pd.Series(False, index=dataframe.index)),
            # 2. BTC bull regime
            dataframe["%btc_trend"] >= 0.002,
            # 3. Pair in local uptrend
            dataframe["close"] > dataframe["ema_50"],
            # 4. FreqAI quality gate
            (dataframe["do_predict"] == 1 if "do_predict" in dataframe.columns else pd.Series(True, index=dataframe.index)),
            # 5. Valid candle
            dataframe["volume"] > 0,
            # 6. ATR percentile gate -- top 20% volatility
            (dataframe["atr14_pct_rank"] >= 80.0 if "atr14_pct_rank" in dataframe.columns else pd.Series(True, index=dataframe.index)),
        ]

        entry_signal = reduce(lambda x, y: x & y, conditions)
        dataframe["enter_long"] = 0
        dataframe.loc[entry_signal, "enter_long"] = 1

        # Persist prediction value to enter_tag
        if "&-target" in dataframe.columns:
            dataframe["enter_tag"] = ""
            dataframe.loc[entry_signal, "enter_tag"] = dataframe.loc[entry_signal, "&-target"].apply(
                lambda p: f"prob_{p:.4f}"
            )

        # Debug: log each condition's last-row result
        try:
            cond1 = dataframe["&-target"].iloc[-1] > self.ml_entry_probability if "&-target" in dataframe.columns else False
            cond2 = dataframe["%btc_trend"].iloc[-1] >= 0.002 if "%btc_trend" in dataframe.columns else False
            cond3 = dataframe["close"].iloc[-1] > dataframe["ema_50"].iloc[-1] if "ema_50" in dataframe.columns else False
            cond4 = dataframe["do_predict"].iloc[-1] == 1 if "do_predict" in dataframe.columns else False
            cond5 = dataframe["volume"].iloc[-1] > 0 if "volume" in dataframe.columns else False
            cond6 = (float(dataframe["atr14_pct_rank"].iloc[-1]) >= 80.0) if "atr14_pct_rank" in dataframe.columns else True
            _prob = dataframe["&-target"].iloc[-1] if "&-target" in dataframe.columns else float("nan")
            logger.warning(f"[{metadata['pair']}] entry check: prob={_prob:.4f} vs {self.ml_entry_probability}, cond1={cond1}, cond2={cond2}, cond3={cond3}, cond4={cond4}, cond5={cond5}, cond6_g8_atr80={cond6}")
        except Exception:
            pass

        # Paper Trading Funnel Tracking
        self._pf_candle_count += 1
        atr80_pass = cond6 if 'cond6' in dir() else True
        if atr80_pass:
            self._pf_atr80_pass += 1
        if cond1 and atr80_pass:
            self._pf_prob_pass += 1
        if dataframe["enter_long"].iloc[-1]:
            self._pf_entries += 1
            prob_val = float(dataframe["&-target"].iloc[-1]) if "&-target" in dataframe.columns else 0.0
            if prob_val < 0.60:
                bucket = "0.55-0.60"
            elif prob_val < 0.65:
                bucket = "0.60-0.65"
            elif prob_val < 0.70:
                bucket = "0.65-0.70"
            else:
                bucket = ">0.70"
            self._cal_buckets[bucket]["n"] += 1

        # Daily / checkpoint report
        candles_since_last = self._pf_candle_count - self._pf_last_report
        do_report = (
            candles_since_last >= 288
            or (self._pf_entries >= 10 and not self._checkpoint_fired[10])
            or (self._pf_entries >= 25 and not self._checkpoint_fired[25])
            or (self._pf_entries >= 50 and not self._checkpoint_fired[50])
        )
        if do_report and self._pf_entries > 0:
            self._pf_last_report = self._pf_candle_count
            elapsed_h = (datetime.now() - self._pf_start_time).total_seconds() / 3600
            funnel_msg = (
                f"[PAPER MONITOR] elapsed={elapsed_h:.1f}h candles={self._pf_candle_count} "
                f"atr80_pass={self._pf_atr80_pass} prob_pass={self._pf_prob_pass} "
                f"entries={self._pf_entries} "
                f"roi={self._pf_roi_exits} time_exit={self._pf_time_exits} sl={self._pf_sl_exits}"
            )
            if self._pf_entries >= 10 and not self._checkpoint_fired[10]:
                self._checkpoint_fired[10] = True
                funnel_msg += " >>> CHECKPOINT 10 TRADES <<<"
            if self._pf_entries >= 25 and not self._checkpoint_fired[25]:
                self._checkpoint_fired[25] = True
                funnel_msg += " >>> CHECKPOINT 25 TRADES <<<"
            if self._pf_entries >= 50 and not self._checkpoint_fired[50]:
                self._checkpoint_fired[50] = True
                funnel_msg += " >>> CHECKPOINT 50 TRADES -- EVALUATE FOR PROMOTION <<<"
            logger.warning(funnel_msg)

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
        # Both current_time and trade.open_date are tz-aware in Freqtrade 2026.4.
        # Strip tzinfo from both to allow arithmetic without timezone offset errors.
        current_time_naive = current_time.replace(tzinfo=None)
        open_date_naive = trade.open_date.replace(tzinfo=None)
        hold_minutes = (current_time_naive - open_date_naive).total_seconds() / 60
        if current_profit < 0:
            if hold_minutes > 360:  # 6 hours
                return "time_exit_6h_negative"
        return None

    def on_trade_close(self, pair: str, trade: Trade, order_type: str, **kwargs) -> None:
        """
        Canonical exit snapshot — fires after every trade close regardless of exit reason.
        Captures: exit reason, realized profit, duration, and gate conditions at exit time.
        """
        try:
            current_time = kwargs.get("current_time") or trade.close_date
            open_naive = trade.open_date.replace(tzinfo=None)
            close_naive = current_time.replace(tzinfo=None) if hasattr(current_time, "replace") else current_time
            duration_minutes = (close_naive - open_naive).total_seconds() / 60

            trade_df, _ = self.dp.get_pair_dataframe(pair, self.timeframe)
            signal_candle = trade_df.iloc[-1] if trade_df is not None and len(trade_df) > 0 else None

            gates = self._gate_snapshot(pair, trade_df, signal_candle) if signal_candle is not None else {}

            # ── Paper Trading Monitor — update on exit ──────────────
            exit_reason = trade.exit_reason or "unknown"
            profit = trade.close_profit if trade.close_profit is not None else 0.0
            is_win = profit > 0
            # Update calibration bucket
            bucket = None
            for b in [">0.70", "0.65-0.70", "0.60-0.65", "0.55-0.60"]:
                if b in self._cal_buckets and self._cal_buckets[b]["n"] > 0:
                    # Find the bucket this trade belonged to (stored in gates at entry)
                    entry_prob = gates.get("model_output", 0.0)
                    if b == "0.55-0.60" and entry_prob < 0.60:
                        bucket = b
                    elif b == "0.60-0.65" and 0.60 <= entry_prob < 0.65:
                        bucket = b
                    elif b == "0.65-0.70" and 0.65 <= entry_prob < 0.70:
                        bucket = b
                    elif b == ">0.70" and entry_prob >= 0.70:
                        bucket = b
                    if bucket:
                        self._cal_buckets[bucket]["wins"] += int(is_win)
                        self._cal_buckets[bucket]["pnl"] += profit
                        break
            # Update exit counters
            if exit_reason and exit_reason.startswith("roi"):
                self._pf_roi_exits += 1
            elif exit_reason == "time_exit_6h_negative":
                self._pf_time_exits += 1
            elif exit_reason == "stoploss":
                self._pf_sl_exits += 1

            self._write_snapshot({
                "event": "exit",
                "ts": close_naive.isoformat() if hasattr(close_naive, "isoformat") else str(close_naive),
                "pair": pair,
                "trade_id": trade.id,
                "exit_reason": exit_reason,
                "profit": profit,
                "profit_abs": trade.close_profit_abs,
                "duration_minutes": duration_minutes,
                **gates,
            })
        except Exception as e:
            logger.warning(f"[{pair}] on_trade_close snapshot failed: {e}")

    # =========================================================================
    # GARCH + GATE HELPERS — for entry/exit snapshots
    # =========================================================================

    def _garch_persistence(self, pair: str) -> dict:
        """
        Compute GARCH(1,1) persistence = alpha + beta for the pair's close series.
        Returns {lr, lvl, persist} where persist = alpha + beta.
        persistence >= 1 means a shock is permanent (bad — don't trade).
        persistence >= 3 (accumulated over 3 consecutive 5m candles) is the g2 threshold.
        """
        try:
            import arch
        except ImportError:
            return {"lr": None, "lvl": None, "persist": None}

        try:
            btc_df = self.dp.get_pair_dataframe("BTC/USDT", "5m")
            if btc_df is None or len(btc_df) < 50:
                return {"lr": None, "lvl": None, "persist": None}
            btc_close = btc_df["close"].dropna().astype(float).values
            returns = 100 * np.diff(np.log(btc_close))
            if len(returns) < 20:
                return {"lr": None, "lvl": None, "persist": None}
            model = arch.arch_model(returns[-100:], vol="Garch", p=1, q=1, dist="normal")
            res = model.fit(disp="off", options={"maxiter": 200})
            alpha = float(res.params.get("alpha[1]", 0))
            beta = float(res.params.get("beta[1]", 0))
            lr = float(res.params.get("mu", 0))
            persist = alpha + beta
            # GARCH level (conditional vol squared) at last observation
            cond_var = res.forecast(reindex=False).variance.values[-1, 0]
            lvl = float(cond_var) if cond_var is not None else None
            return {"lr": lr, "lvl": lvl, "persist": persist}
        except Exception:
            return {"lr": None, "lvl": None, "persist": None}

    def _gate_snapshot(self, pair: str, dataframe: DataFrame, signal_candle) -> dict:
        """
        Capture all gate values at the moment of entry or exit decision.
        Returns a dict with GARCH state, BTC trend, model output, and all gate booleans.

        This record is written to trade_snapshots_v6.jsonl for every entry and exit,
        creating an audit trail that links gate states to realized P&L.
        """
        btc_df = self.dp.get_pair_dataframe("BTC/USDT", "5m")
        btc_trend = None
        if btc_df is not None and len(btc_df) >= 21:
            btc_ema21 = ta.EMA(btc_df["close"], timeperiod=21)
            btc_trend = float(btc_df["close"].iloc[-1] / btc_ema21.iloc[-1] - 1)

        # Read &-target (regression value) — the model's vol expansion estimate
        prob = float(signal_candle["&-target"]) if "&-target" in signal_candle else None

        garch = self._garch_persistence(pair)
        persist = garch.get("persist")
        garch_lvl = garch.get("lvl")
        garch_lr = garch.get("lr")

        # g1: model threshold gate
        g1_passed = (prob is not None) and (prob > self.ml_entry_probability)
        # g2: GARCH persistence accumulation — persist >= 1 means vol clustering
        g2_blocked = (persist is not None) and (persist >= 1)
        # g3: model output extremely high — could indicate overfitting to training regime
        g3_blocked = (prob is not None) and (prob > 0.85)
        # g4: BTC trend gate
        g4_passed = (btc_trend is not None) and (btc_trend >= 0.002)
        # g5: do_predict quality gate
        do_predict = int(signal_candle["do_predict"]) if "do_predict" in signal_candle else 0
        g5_passed = (do_predict == 1)
        # g6: volume gate
        g6_passed = (float(signal_candle.get("volume", 0)) > 0) if "volume" in signal_candle else False
        # g7: EMA50 pair momentum
        ema50 = float(signal_candle.get("ema_50", 0))
        close = float(signal_candle.get("close", 0))
        g7_passed = (ema50 > 0) and (close > ema50)
        # g8: ATR percentile rank — only enter when volatility is elevated (top 20%%)
        atr_rank = float(signal_candle.get("atr14_pct_rank", 0))
        g8_passed = (atr_rank >= 80.0)

        return {
            # Model output
            "model_output": prob,
            "model_threshold": self.ml_entry_probability,
            "g1_passed": g1_passed,
            # GARCH
            "garch_persist": persist,
            "garch_level": garch_lvl,
            "garch_lr": garch_lr,
            "g2_blocked": g2_blocked,
            "g3_blocked": g3_blocked,
            # BTC regime
            "btc_trend": btc_trend,
            "g4_passed": g4_passed,
            # Quality gates
            "do_predict": do_predict,
            "g5_passed": g5_passed,
            "g6_passed": g6_passed,
            # Momentum
            "ema50": ema50,
            "close": close,
            "g7_passed": g7_passed,
            "atr14_pct_rank": atr_rank,
            "g8_passed": g8_passed,
        }

    def _write_snapshot(self, record: dict):
        """Append a JSON snapshot to the trade log file. Injects strategy metadata."""
        try:
            # FIX: use /freqtrade/user_data/ directly — this is the container mount point
            # and is always valid regardless of how self.user_data_dir resolves.
            # self.user_data_dir can resolve to the host bind-mount path when running
            # inside Docker (e.g. /home/shad/.../user_data), which causes silent write
            # failures when that path doesn't exist inside the container.
            log_path = "/freqtrade/user_data/logs/trade_snapshots_v6.jsonl"
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            record = {**self._snapshot_meta, **record}
            with open(log_path, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.warning(f"[snapshot] Failed to write snapshot: {e}")

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

        # Guard: require &-target column (regression value from XGBRegressor)
        if "&-target" not in signal_candle:
            logger.warning(f"[{pair}] No &-target column — no entries")
            return False

        # Gate 1: model output threshold
        prob = float(signal_candle["&-target"])
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
        entry_tag = f"prob_{prob:.4f}"

        # ── Entry snapshot (immutable record of conditions at moment of entry) ──
        gates = self._gate_snapshot(pair, dataframe, signal_candle)
        self._write_snapshot({
            "event": "entry",
            "ts": current_time.isoformat() if hasattr(current_time, "isoformat") else str(current_time),
            "pair": pair,
            "strategy_version": "6.1",
            "model_output": prob,
            "btc_trend": btc_trend,
            **gates,
        })

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
        # FIX: read &-target (v4.4 probability column), not "1" (FreqAI column that v4.4 never writes)
        if "&-target" not in dataframe.columns:
            return proposed_stake

        prob = float(signal_candle["&-target"])
        confidence_multiplier = np.clip(1.0 + (prob - self.ml_entry_probability) * 2.5, 0.5, 1.5)
        return np.clip(proposed_stake * confidence_multiplier, min_stake, max_stake)