"""
reporting.py — Leah Evaluation Harness
Standardized HTML + CSV reporting for all experiments.
"""

from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


def generate_html_report(
    experiment_id: str,
    experiment_title: str,
    hypothesis: str,
    null_hypothesis: str,
    params: dict[str, Any],
    results_df: pd.DataFrame,
    best_row: dict,
    recommendation: str,
    manifest: dict,
    output_dir: str = "reports",
) -> str:
    """Generate a self-contained HTML report."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_id = f"{experiment_id}_{ts}"
    output_path = Path(output_dir) / f"{report_id}.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine which columns exist in results_df
    available = list(results_df.columns)
    metric_cols = [c for c in [
        "param_value", "threshold", "trades", "wins", "losses", "win_rate_pct",
        "avg_win", "avg_loss", "profit_factor", "total_pnl",
        "expectancy", "max_drawdown", "max_drawdown_pct",
        "breakeven_win_rate", "median_trade", "rank"
    ] if c in available]

    if "rank" not in results_df.columns:
        results_df = results_df.copy()
        results_df["rank"] = range(1, len(results_df) + 1)

    # Format helpers
    def fmt(val, col):
        if not isinstance(val, (int, float)) or val == "—" or val is None:
            return str(val)
        if col in ("expectancy", "total_pnl"):
            sign = "+" if val >= 0 else ""
            return f"{sign}{val:.4f}"
        if col in ("profit_factor",):
            return f"{val:.3f}"
        if col in ("win_rate_pct", "max_drawdown_pct", "breakeven_win_rate"):
            return f"{val:.2f}%"
        if col in ("avg_win", "avg_loss"):
            sign = "+" if val >= 0 else ""
            return f"{sign}{val:.4f}"
        if isinstance(val, float):
            return f"{val:.4f}"
        return str(val)

    rows_html = ""
    for _, row in results_df.iterrows():
        is_best = int(row.get("rank", 99)) == 1
        cells = "".join(f"<td>{fmt(row.get(c, '—'), c)}</td>" for c in metric_cols)
        rows_html += f"<tr class='{'best' if is_best else ''}'>{cells}</tr>"

    best_thresh = best_row.get("param_value", best_row.get("threshold", "N/A"))
    best_exp = best_row.get("expectancy", 0)
    best_pf = best_row.get("profit_factor", 0)
    best_dd = best_row.get("max_drawdown_pct", 0)
    best_trades = int(best_row.get("trades", 0))

    summary_cards = f"""
    <div class="summary-grid">
        <div class="card">
            <div class="card-label">Best Threshold</div>
            <div class="card-value">{best_thresh}</div>
        </div>
        <div class="card">
            <div class="card-label">Primary Metric</div>
            <div class="card-value">{manifest.get('decision_metric', 'expectancy').upper()}</div>
        </div>
        <div class="card">
            <div class="card-label">Best Value</div>
            <div class="card-value {'positive' if best_exp > 0 else 'negative'}">{best_exp:+.4f}</div>
        </div>
        <div class="card">
            <div class="card-label">Profit Factor</div>
            <div class="card-value {'positive' if best_pf > 1 else 'negative'}">{best_pf:.3f}</div>
        </div>
        <div class="card">
            <div class="card-label">Trades</div>
            <div class="card-value">{best_trades}</div>
        </div>
        <div class="card">
            <div class="card-label">Max Drawdown</div>
            <div class="card-value {'negative' if best_dd > 0 else ''}">{best_dd:.1f}%</div>
        </div>
    </div>
    """

    params_html = "".join(
        f'<div class="param-item"><div class="param-key">{k}</div><div class="param-val">{v}</div></div>'
        for k, v in params.items()
    )

    manifest_rows = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>"
        for k, v in manifest.items()
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{experiment_id}: {experiment_title}</title>
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --muted: #7d8590; --accent: #2f81f7;
    --green: #3fb950; --red: #f85149; --yellow: #d29922;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; color: var(--accent); }}
  .subtitle {{ color: var(--muted); font-size: 0.875rem; margin-bottom: 2rem; }}
  .badge {{ display: inline-block; padding: 0.125rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }}
  .badge-completed {{ background: #0f3020; color: var(--green); }}
  .badge-running {{ background: #2a1f00; color: var(--yellow); }}
  .badge-planned {{ background: #0d1f2d; color: var(--accent); }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 1rem; }}
  .card-label {{ font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.25rem; }}
  .card-value {{ font-size: 1.25rem; font-weight: 600; }}
  .card-value.positive {{ color: var(--green); }}
  .card-value.negative {{ color: var(--red); }}
  h2 {{ font-size: 1rem; margin: 1.5rem 0 0.75rem; color: var(--text); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; font-size: 0.8rem; }}
  th {{ text-align: left; padding: 0.5rem 0.75rem; background: var(--surface); border-bottom: 1px solid var(--border); color: var(--muted); font-weight: 600; text-transform: uppercase; font-size: 0.65rem; letter-spacing: 0.05em; white-space: nowrap; }}
  td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid #21262d; white-space: nowrap; }}
  tr:hover td {{ background: #1c2128; }}
  tr.best td {{ background: #0f3020; }}
  tr.best td:first-child {{ font-weight: 700; color: var(--green); }}
  .recommendation-box {{ background: #0f3020; border: 1px solid var(--green); border-radius: 6px; padding: 1rem 1.25rem; margin: 1.5rem 0; }}
  .recommendation-box h3 {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--green); margin-bottom: 0.5rem; }}
  .recommendation-box p {{ font-size: 0.9rem; }}
  .manifest-table {{ font-size: 0.8rem; }}
  .manifest-table td {{ padding: 0.35rem 0.75rem; }}
  .manifest-table td:first-child {{ color: var(--muted); width: 160px; }}
  .params-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.5rem; margin-bottom: 1.5rem; }}
  .param-item {{ background: var(--surface); border: 1px solid var(--border); border-radius: 4px; padding: 0.5rem 0.75rem; font-size: 0.8rem; }}
  .param-key {{ color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  .param-val {{ color: var(--accent); font-weight: 600; }}
  .footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.75rem; }}
</style>
</head>
<body>
<div class="container">
<h1>{experiment_id}: {experiment_title}</h1>
<div class="subtitle">
  Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC &nbsp;|&nbsp;
  Hypothesis: {hypothesis} &nbsp;|&nbsp;
  <span class="badge badge-{manifest.get('status', 'completed')}">{manifest.get('status', 'completed')}</span>
</div>

{summary_cards}

<div class="recommendation-box">
  <h3>Recommendation</h3>
  <p>{recommendation}</p>
</div>

<h2>Parameters</h2>
<div class="params-grid">{params_html}</div>

<h2>Full Sweep Results</h2>
<table>
  <thead><tr>{"".join(f"<th>{c}</th>" for c in metric_cols)}</tr></thead>
  <tbody>{rows_html}</tbody>
</table>

<h2>Experiment Manifest</h2>
<table class="manifest-table">
  <tbody>
  <tr><td>experiment_id</td><td>{experiment_id}</td></tr>
  <tr><td>hypothesis</td><td>{hypothesis}</td></tr>
  <tr><td>null_hypothesis</td><td>{null_hypothesis}</td></tr>
  <tr><td>decision_metric</td><td>{manifest.get('decision_metric', 'expectancy')}</td></tr>
  <tr><td>secondary_metrics</td><td>{', '.join(manifest.get('secondary_metrics', []))}</td></tr>
  <tr><td>status</td><td>{manifest.get('status', 'completed')}</td></tr>
  <tr><td>generated</td><td>{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</td></tr>
  <tr><td>report_file</td><td>{report_id}.html</td></tr>
  </tbody>
</table>

<div class="footer">
  Leah Evaluation Harness &nbsp;|&nbsp; leah-eval/ &nbsp;|&nbsp; Automated experiment reporting
</div>
</div>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)

    # Also save CSV
    csv_path = output_path.with_suffix(".csv")
    results_df.to_csv(csv_path, index=False)

    return str(output_path)


def save_results_csv(df: pd.DataFrame, experiment_id: str, output_dir: str = "reports") -> str:
    """Save results as CSV."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_id = f"{experiment_id}_{ts}"
    output_path = Path(output_dir) / f"{report_id}_results.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return str(output_path)
