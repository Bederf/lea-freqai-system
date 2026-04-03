#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

FREQTRADE_BIN="${ROOT_DIR}/.venv/bin/freqtrade"
RESULTS_ROOT="${ROOT_DIR}/user_data/backtest_results/current-bots"

declare -A CONFIGS=(
    [lea]="user_data/config.json"
    [finagent]="user_data/config_finagent.json"
    [diagnostic]="user_data/config_diagnostic.json"
    [bbrsi]="user_data/config_bbrsi.json"
)

declare -A STRATEGIES=(
    [lea]="LeaFreqAIStrategy"
    [finagent]="FinAgentStrategy_v2_RiskManaged"
    [diagnostic]="DiagnosticStrategy"
    [bbrsi]="BBRSI"
)

declare -A DEFAULT_HYPEROPT_SPACES=(
    [lea]="roi"
    [finagent]="roi"
    [diagnostic]="roi stoploss"
    [bbrsi]="roi stoploss"
)

declare -A NOTES=(
    [lea]="FreqAI bot. Start with ROI only because exit logic is custom and operationally tuned."
    [finagent]="FreqAI bot with custom_stoploss. Start with ROI only before touching stoploss behavior."
    [diagnostic]="Reference bot. ROI and stoploss are reasonable first-pass spaces."
    [bbrsi]="Simple non-FreqAI bot. ROI and stoploss are the cleanest starting spaces."
)

BOTS=(lea finagent diagnostic bbrsi)

usage() {
    cat <<'EOF'
Usage:
  scripts/research_bots.sh plan
  scripts/research_bots.sh backtest <bot|all> <timerange> [extra freqtrade args...]
  scripts/research_bots.sh hyperopt <bot|all> <timerange> <epochs> [spaces...]

Examples:
  scripts/research_bots.sh plan
  scripts/research_bots.sh backtest lea 20260201-20260326
  scripts/research_bots.sh backtest all 20260101-20260326 --cache none
  scripts/research_bots.sh hyperopt bbrsi 20260101-20260326 100
  scripts/research_bots.sh hyperopt diagnostic 20260101-20260326 80 roi stoploss

Notes:
  - Results are written under user_data/backtest_results/current-bots/<bot>/.
  - Hyperopt defaults are intentionally conservative for the current live strategies.
  - FreqAI strategies will take materially longer than BBRSI.
EOF
}

ensure_bot() {
    local bot="$1"
    if [[ -z "${CONFIGS[$bot]:-}" ]]; then
        echo "Unknown bot: ${bot}" >&2
        echo "Expected one of: ${BOTS[*]} or all" >&2
        exit 1
    fi
}

ensure_freqtrade() {
    if [[ ! -x "$FREQTRADE_BIN" ]]; then
        echo "Missing freqtrade executable at $FREQTRADE_BIN" >&2
        exit 1
    fi
}

show_plan() {
    printf "%-11s %-38s %-34s %s\n" "bot" "strategy" "default_hyperopt_spaces" "notes"
    printf "%-11s %-38s %-34s %s\n" "-----------" "--------------------------------------" "----------------------------------" "-----"
    for bot in "${BOTS[@]}"; do
        printf "%-11s %-38s %-34s %s\n" \
            "$bot" \
            "${STRATEGIES[$bot]}" \
            "${DEFAULT_HYPEROPT_SPACES[$bot]}" \
            "${NOTES[$bot]}"
    done
}

run_backtest_one() {
    local bot="$1"
    local timerange="$2"
    shift 2

    local result_dir="${RESULTS_ROOT}/${bot}"
    mkdir -p "$result_dir"

    echo "==> Backtesting ${bot} (${STRATEGIES[$bot]}) timerange=${timerange}"
    "$FREQTRADE_BIN" backtesting \
        --config "${CONFIGS[$bot]}" \
        --config "user_data/config_backtest_override_freqai.json" \
        --strategy "${STRATEGIES[$bot]}" \
        --timerange "$timerange" \
        --export trades \
        --breakdown day week month \
        --backtest-directory "$result_dir" \
        --notes "current-bots ${bot} ${timerange}" \
        "$@"
}

run_hyperopt_one() {
    local bot="$1"
    local timerange="$2"
    local epochs="$3"
    shift 3

    local -a spaces=()
    if [[ "$#" -gt 0 ]]; then
        spaces=("$@")
    else
        # shellcheck disable=SC2206
        spaces=(${DEFAULT_HYPEROPT_SPACES[$bot]})
    fi

    echo "==> Hyperopting ${bot} (${STRATEGIES[$bot]}) timerange=${timerange} epochs=${epochs} spaces=${spaces[*]}"
    "$FREQTRADE_BIN" hyperopt \
        --config "${CONFIGS[$bot]}" \
        --strategy "${STRATEGIES[$bot]}" \
        --timerange "$timerange" \
        --epochs "$epochs" \
        --spaces "${spaces[@]}" \
        --hyperopt-loss SharpeHyperOptLossDaily \
        --job-workers -1 \
        --min-trades 10 \
        --ignore-missing-spaces
}

main() {
    ensure_freqtrade

    if [[ "$#" -lt 1 ]]; then
        usage
        exit 1
    fi

    local command="$1"
    shift

    case "$command" in
        plan)
            show_plan
            ;;
        backtest)
            if [[ "$#" -lt 2 ]]; then
                usage
                exit 1
            fi
            local bot="$1"
            local timerange="$2"
            shift 2

            if [[ "$bot" == "all" ]]; then
                for current_bot in "${BOTS[@]}"; do
                    run_backtest_one "$current_bot" "$timerange" "$@"
                done
            else
                ensure_bot "$bot"
                run_backtest_one "$bot" "$timerange" "$@"
            fi
            ;;
        hyperopt)
            if [[ "$#" -lt 3 ]]; then
                usage
                exit 1
            fi
            local bot="$1"
            local timerange="$2"
            local epochs="$3"
            shift 3

            if [[ "$bot" == "all" ]]; then
                for current_bot in "${BOTS[@]}"; do
                    run_hyperopt_one "$current_bot" "$timerange" "$epochs" "$@"
                done
            else
                ensure_bot "$bot"
                run_hyperopt_one "$bot" "$timerange" "$epochs" "$@"
            fi
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"
