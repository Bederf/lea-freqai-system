"""
Bandit event log summary report.

Reads JSONL events from user_data/bandit_selections.jsonl and prints:
- event counts
- entry confirmation/rejection rates
- reject reason distribution
- exit reason distribution
- context/strategy breakdowns
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List


def _safe_pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return 100.0 * numerator / denominator


def load_events(path: Path) -> List[dict]:
    events: List[dict] = []
    if not path.exists():
        return events

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                row = json.loads(s)
            except json.JSONDecodeError:
                # Ignore malformed lines to keep the report resilient.
                continue
            if isinstance(row, dict):
                row["_line"] = line_no
                events.append(row)
    return events


def summarize(events: List[dict], limit_contexts: int = 12) -> None:
    event_counts = Counter()
    reject_reasons = Counter()
    exit_reasons = Counter()

    confirmed_by_strategy = Counter()
    rejected_by_strategy = Counter()

    confirmed_by_context = Counter()
    rejected_by_context = Counter()

    context_strategy_confirmed: Dict[str, Counter] = defaultdict(Counter)
    context_strategy_rejected: Dict[str, Counter] = defaultdict(Counter)

    legacy_selection_count = 0

    for e in events:
        event_type = e.get("event_type")

        # Backward compatibility for legacy selection rows without event_type.
        if event_type is None and {"pair", "context", "strategy", "entry_tag"}.issubset(e.keys()):
            event_type = "selection_legacy"
            legacy_selection_count += 1

        if not event_type:
            event_type = "unknown"

        event_counts[event_type] += 1

        strategy = str(e.get("strategy", "unknown"))
        context = str(e.get("context", "unknown"))

        if event_type == "entry_confirmed":
            confirmed_by_strategy[strategy] += 1
            confirmed_by_context[context] += 1
            context_strategy_confirmed[context][strategy] += 1
        elif event_type == "entry_rejected":
            rejected_by_strategy[strategy] += 1
            rejected_by_context[context] += 1
            context_strategy_rejected[context][strategy] += 1
            reject_reasons[str(e.get("reason", "unknown"))] += 1
        elif event_type == "exit_trigger":
            exit_reasons[str(e.get("exit_reason", "unknown"))] += 1

    total_conf = sum(confirmed_by_strategy.values())
    total_rej = sum(rejected_by_strategy.values())
    total_attempts = total_conf + total_rej

    print("=" * 72)
    print("BANDIT EVENT REPORT")
    print("=" * 72)
    print(f"Total log lines parsed: {len(events)}")
    if legacy_selection_count:
        print(f"Legacy selection-only lines: {legacy_selection_count}")
    print()

    print("Event counts:")
    for k, v in event_counts.most_common():
        print(f"  - {k:20s} {v:>7d}")
    print()

    print("Entry confirmation:")
    print(f"  - confirmed: {total_conf}")
    print(f"  - rejected : {total_rej}")
    print(f"  - attempts : {total_attempts}")
    print(f"  - accept % : {_safe_pct(total_conf, total_attempts):.2f}%")
    print()

    if total_attempts:
        print("By strategy:")
        all_strats = sorted(set(confirmed_by_strategy) | set(rejected_by_strategy))
        for s in all_strats:
            c = confirmed_by_strategy[s]
            r = rejected_by_strategy[s]
            t = c + r
            print(
                f"  - {s:12s} confirmed={c:5d} rejected={r:5d} "
                f"accept={_safe_pct(c, t):6.2f}%"
            )
        print()

    if reject_reasons:
        print("Top reject reasons:")
        for reason, count in reject_reasons.most_common(12):
            print(f"  - {reason:28s} {count:>7d}")
        print()

    if exit_reasons:
        print("Exit reasons:")
        for reason, count in exit_reasons.most_common():
            print(f"  - {reason:28s} {count:>7d}")
        print()

    if confirmed_by_context or rejected_by_context:
        print("Top contexts by attempts:")
        attempts_by_context = Counter(confirmed_by_context)
        attempts_by_context.update(rejected_by_context)

        for context, attempts in attempts_by_context.most_common(limit_contexts):
            c = confirmed_by_context[context]
            r = rejected_by_context[context]
            print(
                f"  - {context:36s} attempts={attempts:5d} "
                f"confirmed={c:5d} rejected={r:5d} accept={_safe_pct(c, attempts):6.2f}%"
            )

            conf_split = ", ".join(
                f"{k}:{v}" for k, v in context_strategy_confirmed[context].most_common()
            ) or "none"
            rej_split = ", ".join(
                f"{k}:{v}" for k, v in context_strategy_rejected[context].most_common()
            ) or "none"
            print(f"      confirmed_by_strategy: {conf_split}")
            print(f"      rejected_by_strategy : {rej_split}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize bandit event JSONL logs.")
    parser.add_argument(
        "--log",
        type=str,
        default="user_data/bandit_selections.jsonl",
        help="Path to JSONL event log",
    )
    parser.add_argument(
        "--top-contexts",
        type=int,
        default=12,
        help="Number of contexts to show in context breakdown",
    )
    args = parser.parse_args()

    log_path = Path(args.log)
    events = load_events(log_path)

    if not events:
        print(f"No events found at: {log_path}")
        return

    summarize(events, limit_contexts=max(1, args.top_contexts))


if __name__ == "__main__":
    main()
