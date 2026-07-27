"""
parse_probwatch.py — Leah v6 Gate / Probability Log Parser
===========================================================
Reads freqtrade_lea_v6.log, extracts gate evaluation lines,
and produces a structured gate probability + GARCH ceiling report.

v6 changes vs v5:
  - Gate 0 (GARCH ceiling): h_1 <= 0.6 required for entry
  - Log format adds g0 and garch_level to entry_check lines
  - Regex updated to capture g0, garch_level alongside g1-g5
"""

import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_PATH = Path("/home/shad/lea-freqai-system/user_data/logs/freqtrade_lea_v6.log")
DB_PATH  = Path("/home/shad/lea-freqai-system/user_data/tradesv3_lea_v6.sqlite")
OUT_PATH = Path("/home/shad/.hermes/cron/output/probwatch_check.log")
VALIDATION_LOG = Path("/home/shad/lea-freqai-system/validation_v6_probwatch.log")
MARKER_FILE    = Path("/home/shad/lea-freqai-system/.probwatch_v6_marker")

GARCH_CEILING = 0.60  # v6: h_1 > 0.6 → no entry

# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

ENTRY_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} - LeahAIV5 - WARNING - "
    r"\[(\S+)\] entry check: "
    r"g0=(\w+)\(garch_lvl=([-\d.]+)/([\d.]+)\) "
    r"g1=(\w+)\(garch_lr=([-\d.]+)\) "
    r"g2=(\w+)\(persist=(\d+)\) "
    r"g3=(\w+) "
    r"g4=(\w+) "
    r"g5=(\w+)\(btc_trend=([+-]?\d+\.?\d*)\)"
)

GARCH_UPDATE_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?\[(\S+)\] GARCH updated: "
    r"log_ratio=([-\d.]+) h_1=([-\d.]+)"
)

TRADE_LOG_RE = re.compile(
    r"(trade|enter|exit|buy|sell|profit|close).*"
)

def parse_log_since(since_ts: datetime):
    """Return (garch_entries, garch_updates, errors) from log since timestamp."""
    if not LOG_PATH.exists():
        return [], [], ["LOG NOT FOUND"]

    garch_entries = []   # one row per entry_check WARNING line
    garch_updates = {}   # pair -> (ts, log_ratio, h_1)
    errors = []

    try:
        with open(LOG_PATH, "r") as f:
            for line in f:
                # Parse GARCH update lines
                m_up = GARCH_UPDATE_RE.search(line)
                if m_up:
                    ts_str, pair, log_ratio, h_1 = m_up.groups()
                    try:
                        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        h_1_f = float(h_1)
                        garch_updates[pair] = (ts, float(log_ratio), h_1_f)
                    except ValueError:
                        pass

                # Parse entry check WARNING lines
                if "entry check:" not in line:
                    continue
                m = ENTRY_RE.search(line)
                if not m:
                    continue
                ts_str, pair = m.group(1), m.group(2)
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if ts <= since_ts:
                    continue

                g0_pass   = m.group(3) == "True"
                garch_lvl  = float(m.group(4))
                g1_pass    = m.group(5) == "True"
                garch_lr   = float(m.group(6))
                g2_pass    = m.group(7) == "True"
                persist    = int(m.group(8))
                g3_pass    = m.group(9) == "True"
                g4_pass    = m.group(10) == "True"
                g5_pass    = m.group(11) == "True"
                btc_trend  = float(m.group(12))

                garch_entries.append({
                    "ts": ts,
                    "pair": pair,
                    "g0_pass": g0_pass,
                    "garch_level": garch_lvl,
                    "g1_pass": g1_pass,
                    "garch_lr": garch_lr,
                    "g2_pass": g2_pass,
                    "persist": persist,
                    "g3_pass": g3_pass,
                    "g4_pass": g4_pass,
                    "g5_pass": g5_pass,
                    "btc_trend": btc_trend,
                })
    except Exception as e:
        import traceback
        errors.append(f"Log read error: {e}")
        traceback.print_exc()

    return garch_entries, garch_updates, errors


def get_marker():
    """Read last processed timestamp from marker file."""
    if MARKER_FILE.exists():
        try:
            return datetime.fromisoformat(MARKER_FILE.read_text().strip())
        except Exception:
            pass
    # Default: 24h ago
    return datetime.now(timezone.utc) - timedelta(hours=24)


def save_marker(ts: datetime):
    """Save latest processed timestamp to marker file."""
    MARKER_FILE.write_text(ts.isoformat())


def get_open_trades():
    """Query DB for open trades."""
    if not DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT id, pair, enter_tag, open_rate, stake_amount,
                   datetime(open_date, 'unixepoch', 'localtime')
            FROM trades WHERE is_open = 1
        """)
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def get_recent_closed_trades(limit=5):
    """Query DB for most recent closed trades."""
    if not DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(f"""
            SELECT id, pair, enter_tag, close_profit_abs, exit_reason,
                   datetime(open_date, 'unixepoch', 'localtime'),
                   datetime(close_date, 'unixepoch', 'localtime')
            FROM trades WHERE is_open = 0
            ORDER BY close_date DESC LIMIT {limit}
        """)
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def fmt_garch(level):
    """Color-coded GARCH level string."""
    if level <= 0.4:
        return f"{level:.4f} 🟢"
    elif level <= 0.6:
        return f"{level:.4f} 🟡"
    else:
        return f"{level:.4f} 🔴"


def make_table(entries):
    """Build gate probability table from parsed entries."""
    if not entries:
        return "  No entry evaluations in this window.\n"

    # Group by pair
    from collections import defaultdict
    by_pair = defaultdict(list)
    for e in entries:
        by_pair[e["pair"]].append(e)

    lines = []
    header = (f"  {'Pair':<12} {'Time':<8} {'GARCH_lvl':>14}  {'g0':>4} {'g1':>5} {'g2':>6} "
              f"{'g3':>4} {'g4':>4} {'g5':>4}  {'btc_trend':>10}  Pass?")
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))

    for pair in sorted(by_pair.keys()):
        evals = sorted(by_pair[pair], key=lambda x: x["ts"])
        for e in evals:
            g0 = "✅" if e["g0_pass"] else "❌"
            g1 = "✅" if e["g1_pass"] else "❌"
            g2 = "✅" if e["g2_pass"] else "❌"
            g3 = "✅" if e["g3_pass"] else "❌"
            g4 = "✅" if e["g4_pass"] else "❌"
            g5 = "✅" if e["g5_pass"] else "❌"
            ts = e["ts"].strftime("%H:%M:%S")
            g_lvl = fmt_garch(e["garch_level"])
            all_pass = all([e["g0_pass"], e["g1_pass"], e["g2_pass"],
                             e["g3_pass"], e["g4_pass"], e["g5_pass"]])
            marker = " ✅ ENTRY" if all_pass else ""
            lines.append(
                f"  {e['pair']:<12} {ts:<8} {g_lvl:>14}  {g0:>4} {g1:>5} {g2:>6} "
                f"{g3:>4} {g4:>4} {g5:>4}  {e['btc_trend']:>+10.4f}  "
                f"{'(CEILING)' if not e['g0_pass'] else ''}{marker}"
            )

    return "\n".join(lines)


def gate_summary_table(entries):
    """Gate pass rate summary across all evaluated pairs."""
    if not entries:
        return "  No entries.\n"
    n = len(entries)
    g0_fails = sum(1 for e in entries if not e["g0_pass"])
    g1_fails = sum(1 for e in entries if not e["g1_pass"])
    g2_fails = sum(1 for e in entries if not e["g2_pass"])
    g5_fails = sum(1 for e in entries if not e["g5_pass"])
    all_pass = sum(1 for e in entries if all([e["g0_pass"], e["g1_pass"], e["g2_pass"],
                                               e["g3_pass"], e["g4_pass"], e["g5_pass"]]))

    # Stats on GARCH level for this window
    levels = [e["garch_level"] for e in entries]
    max_lvl = max(levels)
    min_lvl = min(levels)
    avg_lvl = sum(levels) / len(levels)

    lines = [
        f"  Gate Summary (n={n} evaluations across all pairs):",
        f"  g0 (GARCH ceiling ≤{GARCH_CEILING}):  FAILS={g0_fails} ({g0_fails/n*100:.1f}%)",
        f"  g1 (GARCH log_ratio >0.05):   FAILS={g1_fails} ({g1_fails/n*100:.1f}%)",
        f"  g2 (persist ≥3 candles):        FAILS={g2_fails} ({g2_fails/n*100:.1f}%)",
        f"  g5 (BTC trend ≥0.002):          FAILS={g5_fails} ({g5_fails/n*100:.1f}%)",
        f"  All gates passed (entries):     {all_pass} ({all_pass/n*100:.1f}%)",
        f"  GARCH level range this window:  min={min_lvl:.4f}  max={max_lvl:.4f}  avg={avg_lvl:.4f}",
        f"  GARCH ceiling threshold:         {GARCH_CEILING}  (v6 hard gate)",
    ]
    return "\n".join(lines)


def format_open_trades(trades):
    if not trades:
        return "  None"
    lines = []
    for t in trades:
        lines.append(f"  id={t[0]} {t[1]} tag={t[2]} @ {t[3]:.4f}  opened {t[5]}")
    return "\n".join(lines)


def format_closed_trades(trades):
    if not trades:
        return "  None"
    lines = []
    for t in trades:
        profit_str = f"${t[3]:+.4f}" if t[3] is not None else "$?"
        lines.append(
            f"  id={t[0]} {t[1]:<10} {profit_str:>10}  exit={t[4][:30]:<30}  "
            f"open={t[5]}  close={t[6]}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# v6 validation log append
# ---------------------------------------------------------------------------

def append_validation_log(entries: list, since_ts: datetime):
    """Append gate evaluations to validation log for later analysis."""
    lines = []
    for e in entries:
        lines.append(
            f"{e['ts'].isoformat()}Z|{e['pair']}|{e['garch_level']:.4f}|"
            f"{int(e['g0_pass'])}|{e['garch_lr']:.4f}|{int(e['g1_pass'])}|"
            f"{e['persist']}|{int(e['g2_pass'])}|{int(e['g5_pass'])}|{e['btc_trend']:+.4f}"
        )
    if not lines:
        return
    with open(VALIDATION_LOG, "a") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------

def generate_report():
    since_ts = get_marker()
    entries, garch_updates, errors = parse_log_since(since_ts)
    now = datetime.now(timezone.utc)

    if entries:
        latest_ts = max(e["ts"] for e in entries)
    elif garch_updates:
        latest_ts = max(ts for ts, _, _ in garch_updates.values())
    else:
        latest_ts = since_ts

    # Save marker
    save_marker(latest_ts)

    # Append to validation log
    if entries:
        append_validation_log(entries, since_ts)

    # DB queries
    open_trades   = get_open_trades()
    closed_trades = get_recent_closed_trades(5)

    # Open trade count
    open_count = len(open_trades)
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM trades WHERE is_open=0")
        total_closed = cur.fetchone()[0]
        conn.close()
    except Exception:
        total_closed = 0

    # Build report
    report = []
    report.append("")
    report.append(f"=== LeahAI v6 ProbWatch Report ===")
    report.append(f"Generated: {now.isoformat()}")
    report.append(f"Window: {since_ts.isoformat()} → {latest_ts.isoformat()}")
    report.append("")
    report.append("GARCH Level (v6 ceiling gate):")
    report.append(f"  Ceiling threshold: {GARCH_CEILING}  (h_1 > {GARCH_CEILING} → BLOCKED)")
    for pair, (ts, lr, lvl) in sorted(garch_updates.items()):
        status = "OK" if lvl <= GARCH_CEILING else "⚠️ ABOVE CEILING"
        report.append(f"  [{pair}] {ts.strftime('%H:%M:%S')}  h_1={lvl:.4f}  log_ratio={lr:.4f}  {status}")
    report.append("")
    report.append("Gate Evaluation Table:")
    report.append(make_table(entries))
    report.append("")
    report.append(gate_summary_table(entries))
    report.append("")

    # Open trades
    report.append("Open Positions:")
    report.append(format_open_trades(open_trades))
    report.append("")
    report.append(f"Recent Closed Trades (v6 total closed: {total_closed}):")
    report.append(format_closed_trades(closed_trades))
    report.append("")

    # Errors
    if errors:
        report.append("ERRORS:")
        for err in errors:
            report.append(f"  {err}")

    text = "\n".join(report)

    # Write to output log
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(text)

    # Print to stdout (captured by cron)
    print(text)
    return text


if __name__ == "__main__":
    generate_report()
