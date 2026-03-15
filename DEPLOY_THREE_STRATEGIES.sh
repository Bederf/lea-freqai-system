#!/bin/bash
# Deploy Three Strategies in Parallel
# Usage: ./DEPLOY_THREE_STRATEGIES.sh [option]
# Options: lea, finagent, hybrid, all, backtest

set -e

REPO_DIR="/home/bederf/freqtrade"
cd $REPO_DIR

echo "════════════════════════════════════════════════════════════════"
echo "         Three Strategies Deployment Script"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Function to run backtest
backtest_strategy() {
    local strategy=$1
    echo "🔄 Backtesting: $strategy"
    freqtrade backtest \
        --strategy "$strategy" \
        --config config_lea_backtest.json \
        --timerange 20250920-20251027
}

# Function to run live trading
deploy_strategy() {
    local strategy=$1
    echo "🚀 Deploying: $strategy"
    freqtrade trade \
        --strategy "$strategy" \
        --config config.json
}

# Function to run dry-run (paper trading)
dryrun_strategy() {
    local strategy=$1
    echo "📊 Paper Trading: $strategy"
    freqtrade trade \
        --strategy "$strategy" \
        --config config_lea_dryrun.json
}

case "${1:-all}" in
    lea)
        echo "📈 LeaFreqAIStrategy (Growth Focus)"
        echo "   Win Rate: 83.5% | Drawdown: 14.27% | P&L: -10.75%"
        echo ""
        deploy_strategy "LeaFreqAIStrategy"
        ;;
    
    finagent)
        echo "🛡️  FinAgentStrategy_v2_RiskManaged (Safety Focus)"
        echo "   Win Rate: 29.9% | Drawdown: 1.09% | P&L: -1.01%"
        echo ""
        deploy_strategy "FinAgentStrategy_v2_RiskManaged"
        ;;
    
    hybrid)
        echo "🔄 HybridAIStrategy (Testing/Learning)"
        echo "   Win Rate: 75% | Drawdown: 18.76% | P&L: -18.28%"
        echo ""
        deploy_strategy "HybridAIStrategy"
        ;;
    
    backtest)
        echo "🔬 Running Backtests..."
        echo ""
        backtest_strategy "LeaFreqAIStrategy"
        echo ""
        backtest_strategy "FinAgentStrategy_v2_RiskManaged"
        echo ""
        backtest_strategy "HybridAIStrategy"
        echo ""
        echo "✅ All backtests complete"
        ;;
    
    dryrun)
        echo "📊 Running Paper Trading (All Three)..."
        echo ""
        dryrun_strategy "LeaFreqAIStrategy" &
        LEA_PID=$!
        
        dryrun_strategy "FinAgentStrategy_v2_RiskManaged" &
        FIN_PID=$!
        
        dryrun_strategy "HybridAIStrategy" &
        HYB_PID=$!
        
        echo ""
        echo "✅ All three strategies running in paper trading mode"
        echo "   Process IDs: LEA=$LEA_PID, FIN=$FIN_PID, HYB=$HYB_PID"
        echo ""
        wait
        ;;
    
    all)
        echo "🚀 Deploying All Three Strategies in Parallel"
        echo ""
        echo "Terminal 1: LeaFreqAIStrategy (Growth)"
        deploy_strategy "LeaFreqAIStrategy" &
        LEA_PID=$!
        
        sleep 2
        
        echo ""
        echo "Terminal 2: FinAgentStrategy_v2_RiskManaged (Safety)"
        deploy_strategy "FinAgentStrategy_v2_RiskManaged" &
        FIN_PID=$!
        
        sleep 2
        
        echo ""
        echo "Terminal 3: HybridAIStrategy (Testing)"
        deploy_strategy "HybridAIStrategy" &
        HYB_PID=$!
        
        echo ""
        echo "════════════════════════════════════════════════════════════════"
        echo "✅ All three strategies deployed!"
        echo ""
        echo "Process IDs:"
        echo "  LeaFreqAI: $LEA_PID"
        echo "  FinAgent:  $FIN_PID"
        echo "  HybridAI:  $HYB_PID"
        echo ""
        echo "Capital Allocation (Suggested):"
        echo "  LeaFreqAI:   30% (Growth)"
        echo "  FinAgent:    30% (Safety)"
        echo "  HybridAI:    15% (Testing)"
        echo "  Reserve:     25% (Opportunities)"
        echo "════════════════════════════════════════════════════════════════"
        wait
        ;;
    
    *)
        echo "Usage: $0 [option]"
        echo ""
        echo "Options:"
        echo "  lea           - Deploy LeaFreqAIStrategy only"
        echo "  finagent      - Deploy FinAgentStrategy_v2_RiskManaged only"
        echo "  hybrid        - Deploy HybridAIStrategy only"
        echo "  all           - Deploy all three in parallel (live trading)"
        echo "  backtest      - Run backtests for all three"
        echo "  dryrun        - Run paper trading for all three"
        echo ""
        echo "Examples:"
        echo "  ./DEPLOY_THREE_STRATEGIES.sh all        # Deploy all three"
        echo "  ./DEPLOY_THREE_STRATEGIES.sh backtest   # Validate performance"
        echo "  ./DEPLOY_THREE_STRATEGIES.sh lea        # Growth strategy only"
        exit 1
        ;;
esac
