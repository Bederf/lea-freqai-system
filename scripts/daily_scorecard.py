#!/home/bederf/lea-freqai-system/.venv/bin/python3
"""Daily scorecard for the three trading bots."""

from __future__ import annotations

import argparse
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "user_data" / "data" / "binance"


@dataclass(frozen=True)
class BotConfig:
    name: str
    service: str
    db_path: Path
    config_path: Path
    log_path: Path


@dataclass
class OpenTrade:
    trade_id: int
    pair: str
    amount: float
    open_rate: float
    open_date: str
    last_price: float | None
    pnl_abs: float | None
    pnl_pct: float | None


BOTS: tuple[BotConfig, ...] = (
    BotConfig(
        "lea",
        "freqtrade-lea.service",
        ROOT / "user_data" / "tradesv3_lea.sqlite",
        ROOT / "user_data" / "config.json",
        ROOT / "logs" / "freqtrade_lea.log",
    ),
    BotConfig(
        "finagent",
        "freqtrade-finagent.service",
        ROOT / "user_data" / "tradesv3_finagent.sqlite",
        ROOT / "user_data" / "config_finagent.json",
        ROOT / "logs" / "finagent.log",
    ),
    BotConfig(
        "diagnostic",
        "freqtrade-diagnostic.service",
        ROOT / "user_data" / "tradesv3_diagnostic.sqlite",
        ROOT / "user_data" / "config_diagnostic.json",
        ROOT / "logs" / "freqtrade_diagnostic.log",
    ),
    BotConfig(
        "bbrsi",
        "freqtrade-bbrsi.service",
        ROOT / "user_data" / "tradesv3_bbrsi.sqlite",
        ROOT / "user_data" / "config_bbrsi.json",
        ROOT / "logs" / "freqtrade_bbrsi.log",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show a daily scorecard for all bots.")
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Date to summarize in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--no-open-details",
        action="store_true",
        help="Hide per-open-trade detail rows.",
    )
    return parser.parse_args()


HEARTBEAT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - .*Bot heartbeat")


def service_status(bot: BotConfig) -> str:
    if not bot.log_path.exists():
        return "no_log"

    try:
        lines = bot.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "log_error"

    for line in reversed(lines[-500:]):
        match = HEARTBEAT_RE.match(line)
        if not match:
            continue
        heartbeat = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        age_seconds = (datetime.now() - heartbeat).total_seconds()
        if age_seconds <= 180:
            return "running"
        return "stale"
    return "unknown"


def pair_price_path(pair: str) -> Path:
    return DATA_DIR / f"{pair.replace('/', '_')}-5m.feather"


def latest_price(pair: str) -> float | None:
    path = pair_price_path(pair)
    if not path.exists():
        return None
    try:
        df = pd.read_feather(path)
    except Exception:
        return None
    if df.empty or "close" not in df.columns:
        return None
    try:
        return float(df.iloc[-1]["close"])
    except Exception:
        return None


def query_one(cur: sqlite3.Cursor, sql: str, params: Iterable[object] = ()) -> object:
    return cur.execute(sql, tuple(params)).fetchone()[0]


def open_trades(cur: sqlite3.Cursor) -> list[OpenTrade]:
    rows = cur.execute(
        """
        SELECT id, pair, amount, open_rate, open_date
        FROM trades
        WHERE is_open = 1
        ORDER BY open_date
        """
    ).fetchall()

    trades: list[OpenTrade] = []
    for trade_id, pair, amount, open_rate, open_date in rows:
        last = latest_price(pair)
        pnl_abs = None
        pnl_pct = None
        if last is not None and open_rate:
            pnl_abs = float(amount) * (last - float(open_rate))
            pnl_pct = ((last / float(open_rate)) - 1.0) * 100
        trades.append(
            OpenTrade(
                trade_id=int(trade_id),
                pair=str(pair),
                amount=float(amount),
                open_rate=float(open_rate),
                open_date=str(open_date),
                last_price=last,
                pnl_abs=pnl_abs,
                pnl_pct=pnl_pct,
            )
        )
    return trades


def bot_scorecard(bot: BotConfig, target_date: str) -> tuple[dict[str, object], list[OpenTrade]]:
    con = sqlite3.connect(bot.db_path)
    try:
        cur = con.cursor()
        total = int(query_one(cur, "SELECT COUNT(*) FROM trades"))
        open_count = int(query_one(cur, "SELECT COUNT(*) FROM trades WHERE is_open = 1"))
        closed = int(query_one(cur, "SELECT COUNT(*) FROM trades WHERE is_open = 0"))
        entries_today = int(
            query_one(
                cur,
                "SELECT COUNT(*) FROM trades WHERE date(open_date, 'localtime') = ?",
                (target_date,),
            )
        )
        exits_today = int(
            query_one(
                cur,
                """
                SELECT COUNT(*)
                FROM trades
                WHERE close_date IS NOT NULL
                  AND date(close_date, 'localtime') = ?
                """,
                (target_date,),
            )
        )
        pnl_today = float(
            query_one(
                cur,
                """
                SELECT COALESCE(SUM(close_profit_abs), 0)
                FROM trades
                WHERE close_date IS NOT NULL
                  AND date(close_date, 'localtime') = ?
                """,
                (target_date,),
            )
        )
        wins_today = int(
            query_one(
                cur,
                """
                SELECT COUNT(*)
                FROM trades
                WHERE close_date IS NOT NULL
                  AND date(close_date, 'localtime') = ?
                  AND close_profit_abs > 0
                """,
                (target_date,),
            )
        )
        losses_today = int(
            query_one(
                cur,
                """
                SELECT COUNT(*)
                FROM trades
                WHERE close_date IS NOT NULL
                  AND date(close_date, 'localtime') = ?
                  AND close_profit_abs < 0
                """,
                (target_date,),
            )
        )
        realized_total = float(
            query_one(
                cur,
                "SELECT COALESCE(SUM(close_profit_abs), 0) FROM trades WHERE is_open = 0",
            )
        )
        opens = open_trades(cur)
    finally:
        con.close()

    open_pnl = sum(trade.pnl_abs or 0.0 for trade in opens)
    return (
        {
            "status": service_status(bot),
            "total": total,
            "closed": closed,
            "open": open_count,
            "entries_today": entries_today,
            "exits_today": exits_today,
            "wins_today": wins_today,
            "losses_today": losses_today,
            "pnl_today": pnl_today,
            "realized_total": realized_total,
            "open_pnl": open_pnl,
        },
        opens,
    )


def fmt_btc(value: float) -> str:
    return f"{value:+.8f}"


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


def print_summary(target_date: str, show_open_details: bool) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Daily scorecard for {target_date}  generated {now}")
    print("")
    print(
        "bot         status   entries exits wins losses open  pnl_today      "
        "open_pnl      realized_total"
    )
    print(
        "----------  -------  ------- ----- ---- ------ ----  ------------  "
        "------------  --------------"
    )

    all_open_trades: dict[str, list[OpenTrade]] = {}
    for bot in BOTS:
        stats, opens = bot_scorecard(bot, target_date)
        all_open_trades[bot.name] = opens
        print(
            f"{bot.name:<10}  "
            f"{str(stats['status']):<7}  "
            f"{int(stats['entries_today']):>7} "
            f"{int(stats['exits_today']):>5} "
            f"{int(stats['wins_today']):>4} "
            f"{int(stats['losses_today']):>6} "
            f"{int(stats['open']):>4}  "
            f"{fmt_btc(float(stats['pnl_today'])):>12}  "
            f"{fmt_btc(float(stats['open_pnl'])):>12}  "
            f"{fmt_btc(float(stats['realized_total'])):>14}"
        )

    if not show_open_details:
        return

    print("")
    print("Open trades")
    print("----------")
    any_open = False
    for bot in BOTS:
        opens = all_open_trades[bot.name]
        if not opens:
            print(f"{bot.name}: none")
            continue
        any_open = True
        for trade in opens:
            last = "n/a" if trade.last_price is None else f"{trade.last_price:.8f}"
            pnl_abs = "n/a" if trade.pnl_abs is None else fmt_btc(trade.pnl_abs)
            print(
                f"{bot.name}: trade={trade.trade_id} pair={trade.pair} "
                f"opened={trade.open_date} open_rate={trade.open_rate:.8f} "
                f"last={last} pnl={pnl_abs} ({fmt_pct(trade.pnl_pct)})"
            )
    if not any_open:
        print("none")


def main() -> None:
    args = parse_args()
    print_summary(args.date, show_open_details=not args.no_open_details)


if __name__ == "__main__":
    main()
