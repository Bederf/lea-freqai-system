# LEA-FinAgent Hybrid Trading Strategy - Design Document

**Version:** 1.0-alpha
**Date:** 2025-10-26
**Status:** Proposed - Awaiting Implementation & Testing

---

## Executive Summary

This document outlines a hybrid trading strategy that combines:
- **LEA-LSTM**: Deep learning predictions from PyTorch LSTM models
- **FinAgent Framework**: Multi-module decision-making with reflection and memory

### Goals
- Improve win rate from current 83.5% to 87-90%
- Reduce drawdown from 14% to 8-10%
- Increase Sharpe ratio from ~1.2 to 1.5-1.8
- Add market regime awareness for adaptive trading

---

## System Architecture Overview

### Core Components Integration

```python
class LEAFinAgentSystem:
    """
    Combines LEA-LSTM predictions with FinAgent's multi-module decision framework
    """
    def __init__(self):
        # Core LSTM Component (existing)
        self.lstm_model = PyTorchMLPRegressor()

        # FinAgent-inspired Modules (new)
        self.market_analysis = SegmentedAttentionModule()
        self.low_level_reflection = MarketReactionAnalyzer()
        self.high_level_reflection = PerformanceMemory()
        self.auxiliary_tools = NormalizedIndicatorEngine()
        self.decision_maker = CrossAttentionAggregator()
```

---

## 1. Data Flow Pipeline

### Input Processing Layer

**Raw Data Sources:**
- OHLCV data (1m, 5m, 15m, 1h, 4h)
- Order book depth snapshots
- Volume profile analysis
- Funding rates and open interest

**Feature Engineering Pipeline:**
```python
def enhanced_feature_engineering(self, df):
    # Existing LEA-LSTM features
    features = self.calculate_technical_indicators(df)

    # FinAgent-inspired additions
    features['market_regime'] = self.detect_market_regime(df)
    features['volatility_adjusted_signals'] = self.normalize_by_volatility(df)
    features['cross_timeframe_momentum'] = self.multi_timeframe_analysis(df)

    # Microstructure features
    features['order_flow_imbalance'] = self.calculate_ofi(df)
    features['volume_weighted_spread'] = self.vwap_analysis(df)

    return features
```

---

## 2. Market Analysis Module

### Segmented Attention Mechanism

**Purpose:** Divide market data into segments for pattern detection

```python
class SegmentedMarketAnalysis:
    def analyze_market_segments(self, data, segment_size=24):
        """
        Divides market data into segments for pattern detection
        """
        segments = []

        for i in range(0, len(data), segment_size):
            segment = data[i:i+segment_size]

            segment_features = {
                'trend_strength': self.calculate_trend(segment),
                'volatility_regime': self.volatility_classification(segment),
                'volume_pattern': self.volume_analysis(segment),
                'price_action_type': self.classify_price_action(segment)
            }

            attention_score = self.attention_network(segment_features)
            segments.append((segment, attention_score))

        return self.aggregate_segments(segments)
```

**Key Features:**
- Dynamic segmentation based on volatility
- Pattern library maintenance
- Confidence scoring by historical success

---

## 3. Reflection Modules (Dual-Level)

### 3.1 Low-Level Reflection: Immediate Market Response

**Purpose:** Track how market responds to specific patterns

```python
class LowLevelReflection:
    def __init__(self):
        self.reaction_memory = deque(maxlen=1000)
        self.pattern_success_rate = {}

    def analyze_market_reaction(self, pattern, market_response):
        """
        Tracks how market responds to specific patterns
        """
        reaction_metrics = {
            'price_delta': market_response['price_change'],
            'volume_surge': market_response['volume_ratio'],
            'momentum_shift': market_response['momentum_change'],
            'pattern_completion': self.check_pattern_completion(pattern)
        }

        pattern_hash = self.hash_pattern(pattern)
        if pattern_hash not in self.pattern_success_rate:
            self.pattern_success_rate[pattern_hash] = []

        self.pattern_success_rate[pattern_hash].append(reaction_metrics)
        confidence = self.calculate_pattern_confidence(pattern_hash)

        return {
            'pattern': pattern,
            'confidence': confidence,
            'expected_reaction': self.predict_reaction(pattern_hash)
        }
```

**Metrics Tracked:**
- Immediate price reaction (next 1-5 candles)
- Volume response
- Momentum shift
- Pattern completion rate

### 3.2 High-Level Reflection: Strategic Performance Memory

**Purpose:** Evaluate strategy performance across market conditions

```python
class HighLevelReflection:
    def __init__(self):
        self.trade_history = []
        self.strategy_performance = {}
        self.market_regime_performance = {}

    def analyze_strategic_performance(self, recent_trades, market_context):
        """
        Evaluates strategy performance in different market conditions
        """
        regime = market_context['regime']

        performance = {
            'win_rate': self.calculate_win_rate(recent_trades),
            'profit_factor': self.calculate_profit_factor(recent_trades),
            'avg_duration': self.average_trade_duration(recent_trades),
            'risk_reward': self.actual_risk_reward(recent_trades)
        }

        if regime not in self.market_regime_performance:
            self.market_regime_performance[regime] = []

        self.market_regime_performance[regime].append(performance)

        adjustments = self.calculate_strategy_adjustments(regime, performance)
        return adjustments
```

**Performance Dimensions:**
- Win rate by market regime
- Profit factor trends
- Trade duration patterns
- Risk-reward ratios

---

## 4. Auxiliary Tools Module

### Normalized Indicator System

**Purpose:** Convert traditional indicators to normalized signals

```python
class NormalizedIndicatorEngine:
    def process_indicators(self, df):
        """
        Converts traditional indicators to normalized signals (-1 to +1)
        """
        signals = {}

        # RSI normalization (0-100 to -1 to +1)
        rsi = talib.RSI(df['close'])
        signals['rsi_signal'] = (rsi - 50) / 50

        # MACD normalization (z-score)
        macd, signal, hist = talib.MACD(df['close'])
        signals['macd_signal'] = self.z_score_normalize(hist)

        # Bollinger Bands position
        upper, middle, lower = talib.BBANDS(df['close'])
        bb_position = (df['close'] - middle) / (upper - middle)
        signals['bb_signal'] = np.clip(bb_position, -1, 1)

        # Volume analysis
        volume_ratio = df['volume'] / df['volume'].rolling(20).mean()
        signals['volume_signal'] = self.sigmoid_normalize(volume_ratio)

        # Combine with learned weights
        weighted_signal = self.apply_dynamic_weights(signals)
        return weighted_signal

    def apply_dynamic_weights(self, signals):
        """
        Dynamically adjusts indicator weights based on market regime
        """
        weights = self.learn_optimal_weights(signals)
        return sum(s * w for s, w in zip(signals.values(), weights))
```

**Indicators Normalized:**
- RSI → -1 to +1 scale
- MACD histogram → z-score
- Bollinger Band position → relative position
- Volume → surge detection
- Trend strength → momentum score

---

## 5. Decision-Making Module

### Cross-Attention Aggregator

**Purpose:** Integrate all information streams for final decision

```python
class CrossAttentionDecisionMaker:
    def __init__(self):
        self.attention_heads = 4
        self.integration_network = self.build_integration_network()

    def make_trading_decision(self, lstm_pred, market_analysis,
                              reflections, indicator_signals):
        """
        Integrates all information streams for final decision
        """
        # Stage 1: Cross-attention between LSTM and market analysis
        lstm_market_fusion = self.cross_attention(
            query=lstm_pred,
            key=market_analysis['patterns'],
            value=market_analysis['confidence']
        )

        # Stage 2: Integrate reflection insights
        reflection_enhanced = self.cross_attention(
            query=lstm_market_fusion,
            key=reflections['low_level'],
            value=reflections['high_level']
        )

        # Stage 3: Incorporate indicator signals
        final_features = self.cross_attention(
            query=reflection_enhanced,
            key=indicator_signals,
            value=self.prior_knowledge_weights()
        )

        # Generate trading action
        action = self.generate_action(final_features)
        return self.format_trading_decision(action)

    def generate_action(self, features):
        """
        Converts integrated features to trading actions
        """
        action_logits = self.integration_network(features)

        action = {
            'direction': torch.softmax(action_logits[:3], dim=0),  # long/short/neutral
            'size': torch.sigmoid(action_logits[3]) * self.max_position_size,
            'stop_loss': torch.sigmoid(action_logits[4]) * 0.05,  # max 5%
            'take_profit': torch.sigmoid(action_logits[5]) * 0.10  # max 10%
        }

        return self.apply_risk_filters(action)
```

**Decision Process:**
1. Fuse LSTM prediction with market pattern analysis
2. Enhance with reflection insights (pattern memory + performance)
3. Incorporate normalized indicator signals
4. Generate action with risk constraints

---

## 6. Risk Management Layer

### Adaptive Risk Control

```python
class AdaptiveRiskManager:
    def __init__(self):
        self.max_drawdown = 0.10  # 10% max drawdown
        self.position_sizing = KellyCriterion()
        self.correlation_monitor = CorrelationTracker()

    def calculate_position_size(self, signal_strength, market_regime):
        """
        Dynamic position sizing based on multiple factors
        """
        # Kelly Criterion base
        base_size = self.position_sizing.calculate(
            win_rate=signal_strength['expected_win_rate'],
            avg_win=signal_strength['expected_profit'],
            avg_loss=signal_strength['expected_loss']
        )

        # Market regime adjustment
        regime_multiplier = {
            'trending': 1.2,
            'ranging': 0.8,
            'volatile': 0.5,
            'uncertain': 0.3
        }.get(market_regime, 0.5)

        # Correlation risk adjustment
        correlation_adj = self.correlation_monitor.get_adjustment()

        # Portfolio heat check
        current_heat = self.calculate_portfolio_heat()
        heat_multiplier = max(0, 1 - current_heat)

        final_size = base_size * regime_multiplier * correlation_adj * heat_multiplier

        return min(final_size, self.max_position_per_trade)
```

**Risk Controls:**
- Kelly Criterion position sizing
- Market regime adjustments
- Correlation risk monitoring
- Portfolio heat limits
- Maximum position caps

---

## 7. Implementation Phases

### Phase 1: Foundation (Weeks 1-2)
**Status:** Proposed

**Tasks:**
- [ ] Implement normalized indicator system
- [ ] Set up market regime detection
- [ ] Create pattern memory database structure
- [ ] Build basic data pipeline

**Deliverables:**
- Working normalized indicators
- Regime classifier with 5 categories
- Pattern hashing and storage system

### Phase 2: Reflection Modules (Weeks 3-4)
**Status:** Proposed

**Tasks:**
- [ ] Build low-level reflection tracker
- [ ] Implement high-level performance memory
- [ ] Create pattern confidence scoring
- [ ] Add regime-specific performance tracking

**Deliverables:**
- Pattern memory with 100-pattern capacity
- Performance tracking by regime
- Confidence adjustment system

### Phase 3: Integration (Weeks 5-6)
**Status:** Proposed

**Tasks:**
- [ ] Implement cross-attention mechanism
- [ ] Connect all modules
- [ ] Add decision aggregation logic
- [ ] Build risk management layer

**Deliverables:**
- Working hybrid decision system
- Integrated risk management
- Complete trading pipeline

### Phase 4: Optimization (Weeks 7-8)
**Status:** Proposed

**Tasks:**
- [ ] Hyperparameter tuning
- [ ] Latency optimization
- [ ] Memory usage optimization
- [ ] Backtest on historical data

**Deliverables:**
- Optimized hyperparameters
- Performance benchmarks
- Backtest results vs baseline

### Phase 5: Live Testing (Weeks 9-12)
**Status:** Proposed

**Tasks:**
- [ ] Paper trading validation
- [ ] A/B testing against baseline LEA strategy
- [ ] Progressive capital allocation
- [ ] Performance monitoring

**Deliverables:**
- Live performance metrics
- Comparison report
- Production deployment plan

---

## 8. Expected Performance Improvements

### Quantitative Projections

| Metric | Current LEA | FinAgent Paper | **Hybrid Target** |
|--------|-------------|----------------|-------------------|
| Win Rate | 83.5% | 42% | **87-90%** |
| Sharpe Ratio | ~1.2 | ~1.0 | **1.5-1.8** |
| Max Drawdown | 14.27% | ~12% | **8-10%** |
| Profit Factor | ~1.2 | 1.09 | **1.3-1.5** |
| Trades/Month | ~80 | 95 | **60-70** (quality) |

### Key Advantages

1. **Market Regime Awareness**
   - Adapt to trending, ranging, volatile conditions
   - Skip unfavorable periods
   - Expected: -5% to +2% in bear markets (vs current -10.75%)

2. **Pattern Memory**
   - Learn from successful setups
   - Avoid repeating failures
   - Expected: +3-5% win rate improvement

3. **Multi-Timeframe Coherence**
   - Align signals across timeframes
   - Reduce false signals
   - Expected: +2-3% win rate improvement

4. **Adaptive Position Sizing**
   - Scale by confidence
   - Reduce in adverse conditions
   - Expected: +0.2-0.3 Sharpe ratio improvement

---

## 9. Resource Requirements

### Computational Resources

**Minimum Requirements:**
- RAM: 2-3GB (vs 1.9GB current Pi limit)
- CPU: 4+ cores at 1.5GHz+
- Storage: 10GB for pattern database

**Recommended:**
- RAM: 4GB+
- CPU: 8 cores at 2.0GHz+
- GPU: Optional, for faster attention computation

### Data Requirements

**Storage:**
- Pattern memory database: ~500MB
- Performance history: ~200MB
- Market data cache: ~1GB

**Network:**
- API calls: ~100-200 requests/hour
- Data download: ~10MB/hour

---

## 10. Risk Assessment

### Implementation Risks

**High Risk:**
- ❌ Memory constraints on Raspberry Pi (1.9GB total)
- ❌ Complexity may introduce bugs
- ❌ Over-optimization risk

**Medium Risk:**
- ⚠️ Training time for attention modules
- ⚠️ Pattern database management
- ⚠️ Integration with existing FreqAI

**Low Risk:**
- ✅ Normalized indicators (proven technique)
- ✅ Regime detection (well-established)
- ✅ Pattern memory (simple data structure)

### Mitigation Strategies

1. **Memory Constraints**
   - Implement on more powerful hardware first
   - Use ring buffers and data pruning
   - Profile memory usage continuously

2. **Complexity Management**
   - Implement incrementally (phase by phase)
   - Maintain comprehensive tests
   - A/B test each module independently

3. **Over-Optimization**
   - Use walk-forward validation
   - Test on out-of-sample data
   - Monitor live performance closely

---

## 11. Success Metrics

### Phase 1 Success Criteria
- ✅ Normalized indicators implemented and tested
- ✅ Regime detection accuracy > 70%
- ✅ Pattern hashing and retrieval working

### Phase 2 Success Criteria
- ✅ Pattern memory storing and retrieving patterns
- ✅ Confidence adjustments based on history
- ✅ Performance tracking by regime functional

### Phase 3 Success Criteria
- ✅ All modules integrated
- ✅ Decision pipeline end-to-end working
- ✅ Backtest Sharpe > 1.3 (vs 1.2 baseline)

### Phase 4 Success Criteria
- ✅ Backtest win rate > 85%
- ✅ Max drawdown < 12%
- ✅ Profit factor > 1.25

### Phase 5 Success Criteria
- ✅ Paper trading profitable for 30 days
- ✅ Live Sharpe > baseline by 15%
- ✅ Real win rate > 85%

---

## 12. Comparison with Baseline LEA Strategy

### What's New

**Architecture:**
- ❌ Baseline: LSTM predictions only
- ✅ Hybrid: LSTM + pattern memory + regime awareness + reflection

**Decision Making:**
- ❌ Baseline: Single-layer (LSTM → entry)
- ✅ Hybrid: Multi-layer (LSTM → patterns → indicators → decision)

**Risk Management:**
- ❌ Baseline: Fixed 5% stoploss
- ✅ Hybrid: Adaptive based on regime + confidence

**Learning:**
- ❌ Baseline: No memory of past patterns
- ✅ Hybrid: Pattern memory with success tracking

### Backward Compatibility

The hybrid strategy can:
- ✅ Use existing FreqAI infrastructure
- ✅ Use same data sources (via MCP server)
- ✅ Run alongside baseline for A/B testing
- ✅ Fall back to baseline if modules fail

---

## 13. Next Steps

### Immediate Actions (Week 1)

1. **Validate Baseline Performance**
   - Let current LEA strategy run for 1-2 weeks
   - Collect real performance data
   - Identify specific weaknesses

2. **Set Up Development Environment**
   - Clone strategy to new file: `LeaFinAgentStrategy.py`
   - Set up separate config for testing
   - Create development branch in git

3. **Implement Phase 1 (Foundation)**
   - Start with normalized indicators
   - Add basic regime detection
   - Create simple pattern memory

### Medium Term (Weeks 2-4)

4. **Add Reflection Modules**
   - Implement low-level pattern tracking
   - Add performance memory
   - Test confidence adjustments

5. **Backtest Initial Version**
   - Compare against baseline
   - Measure improvement
   - Iterate on weak points

### Long Term (Weeks 5-12)

6. **Full Integration**
   - Add cross-attention if needed
   - Optimize performance
   - Deploy to paper trading

7. **Live Testing**
   - Run alongside baseline
   - A/B test performance
   - Progressive capital allocation

---

## 14. References

**FinAgent Paper:**
- Title: "FinAgent: A Multimodal Foundation Agent for Financial Trading"
- Key Concepts: Segmented attention, dual-level reflection, normalized indicators

**Current LEA Strategy:**
- File: `LeaFreqAIStrategy.py`
- Performance: 83.5% win rate, -10.75% in bear market (+12.44% vs market)
- Documentation: `STOPLOSS_STRATEGY_TESTING.md`, `LEA_STRATEGY_OPTIMIZATION.md`

**FreqAI Documentation:**
- FreqTrade FreqAI integration
- PyTorch models in FreqTrade
- MCP server for real-time data

---

## 15. Appendix: Code Snippets

### A. Normalized Indicator Implementation

```python
def calculate_normalized_indicators(self, dataframe: DataFrame) -> dict:
    signals = {}

    # RSI: 0-100 → -1 to +1
    rsi = ta.RSI(dataframe, timeperiod=14)
    signals['rsi'] = (rsi - 50) / 50

    # MACD: histogram → z-score
    macd = ta.MACD(dataframe)
    hist = macd['macdhist']
    signals['macd'] = (hist - hist.rolling(50).mean()) / (hist.rolling(50).std() + 1e-10)
    signals['macd'] = signals['macd'].clip(-3, 3) / 3

    # Bollinger Bands: position within bands
    bb = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
    bb_pos = (dataframe['close'] - bb['mid']) / ((bb['upper'] - bb['lower']) / 2 + 1e-10)
    signals['bb'] = bb_pos.clip(-1, 1)

    # Volume: surge detection
    vol_ma = dataframe['volume'].rolling(20).mean()
    vol_ratio = dataframe['volume'] / (vol_ma + 1e-10)
    signals['volume'] = np.tanh((vol_ratio - 1) * 2)

    return signals
```

### B. Market Regime Detection

```python
def detect_market_regime(self, dataframe: DataFrame) -> str:
    recent = dataframe.tail(50)

    # Trend strength
    ema_20 = ta.EMA(recent, timeperiod=20)
    ema_50 = ta.EMA(recent, timeperiod=50)
    trend_diff = (ema_20.iloc[-1] - ema_50.iloc[-1]) / ema_50.iloc[-1]

    # Volatility
    atr = ta.ATR(recent, timeperiod=14)
    atr_pct = (atr.iloc[-1] / recent['close'].iloc[-1]) * 100

    # Directional strength
    adx = ta.ADX(recent, timeperiod=14)

    # Classification
    if adx.iloc[-1] > 25 and trend_diff > 0.02:
        return 'trending_up'
    elif adx.iloc[-1] > 25 and trend_diff < -0.02:
        return 'trending_down'
    elif atr_pct > 3.0:
        return 'volatile'
    elif (recent['high'].max() - recent['low'].min()) / recent['close'].mean() < 0.03:
        return 'ranging'
    else:
        return 'uncertain'
```

### C. Pattern Memory System

```python
class PatternMemory:
    def __init__(self):
        self.patterns = deque(maxlen=100)
        self.success_rates = {}

    def hash_pattern(self, features: dict) -> str:
        feature_str = ""
        for key in sorted(features.keys()):
            val = int(features[key] * 10) / 10
            feature_str += f"{key}:{val},"
        return feature_str

    def record_outcome(self, pattern: dict, profit: float):
        pattern_hash = self.hash_pattern(pattern)

        if pattern_hash not in self.success_rates:
            self.success_rates[pattern_hash] = []

        self.success_rates[pattern_hash].append({
            'profit': profit,
            'timestamp': datetime.now()
        })

        # Prune old data (> 30 days)
        cutoff = datetime.now() - timedelta(days=30)
        self.success_rates[pattern_hash] = [
            o for o in self.success_rates[pattern_hash]
            if o['timestamp'] > cutoff
        ]

    def get_confidence(self, pattern: dict) -> float:
        pattern_hash = self.hash_pattern(pattern)

        if pattern_hash not in self.success_rates:
            return 1.0  # Neutral

        outcomes = self.success_rates[pattern_hash]
        if not outcomes:
            return 1.0

        win_rate = sum(1 for o in outcomes if o['profit'] > 0) / len(outcomes)
        return 0.5 + (win_rate * 1.0)  # 0.5 to 1.5 multiplier
```

---

**Document Status:** Draft v1.0
**Last Updated:** 2025-10-26
**Next Review:** After Phase 1 implementation
**Owner:** Development Team
