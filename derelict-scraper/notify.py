#!/usr/bin/env python3
"""
Nightly digest email to admin after scrape + publish run.
Sends via Resend API. Requires RESEND_API_KEY env var.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))
import database

_RESEND_URL   = "https://api.resend.com/emails"
_FROM_ADDRESS = "updates@revive-ireland.com"
_TO_ADDRESS   = "michael.gannon13@gmail.com"


def _fmt_valuation(val) -> str:
    if val is None:
        return "—"
    return f"€{val:,.0f}"


def _build_html(run_date: str, results: list, new_props: list, removed_props: list) -> str:
    ok      = [r for r in results if r["status"] == "ok"]
    errors  = [r for r in results if r["status"] != "ok"]
    total   = sum(r["rows"] for r in ok)

    status_icon  = "✅" if not errors else "⚠️"
    subject_line = f"{status_icon} Revive Ireland — Nightly Scrape {run_date}"

    # Council table rows
    council_rows = ""
    for r in sorted(results, key=lambda x: x["code"]):
        icon = "✓" if r["status"] == "ok" else "✗"
        color = "#2d6a4f" if r["status"] == "ok" else "#c0392b"
        detail = f"{r['rows']} sites" if r["status"] == "ok" else r["error"][:80]
        council_rows += f"""
        <tr>
          <td style="padding:4px 8px;font-family:monospace">{r['code']}</td>
          <td style="padding:4px 8px;color:{color};font-weight:bold">{icon}</td>
          <td style="padding:4px 8px;color:#555">{detail}</td>
        </tr>"""

    # New properties section
    new_section = ""
    if new_props:
        rows_html = "".join(
            f"<tr><td style='padding:4px 8px'>{p['council']}</td>"
            f"<td style='padding:4px 8px'>{p['address']}</td>"
            f"<td style='padding:4px 8px'>{p.get('property_type') or '—'}</td>"
            f"<td style='padding:4px 8px'>{_fmt_valuation(p.get('valuation'))}</td></tr>"
            for p in new_props
        )
        new_section = f"""
        <h3 style="color:#2d6a4f">🆕 New Properties ({len(new_props)})</h3>
        <table style="border-collapse:collapse;width:100%;font-size:13px">
          <tr style="background:#e9f5ee;font-weight:bold">
            <th style="padding:4px 8px;text-align:left">Council</th>
            <th style="padding:4px 8px;text-align:left">Address</th>
            <th style="padding:4px 8px;text-align:left">Type</th>
            <th style="padding:4px 8px;text-align:left">Valuation</th>
          </tr>
          {rows_html}
        </table>"""

    # Removed properties section
    removed_section = ""
    if removed_props:
        rows_html = "".join(
            f"<tr><td style='padding:4px 8px'>{p['council']}</td>"
            f"<td style='padding:4px 8px'>{p['address']}</td></tr>"
            for p in removed_props
        )
        removed_section = f"""
        <h3 style="color:#c0392b">🗑️ Removed from Register ({len(removed_props)})</h3>
        <table style="border-collapse:collapse;width:100%;font-size:13px">
          <tr style="background:#fdecea;font-weight:bold">
            <th style="padding:4px 8px;text-align:left">Council</th>
            <th style="padding:4px 8px;text-align:left">Address</th>
          </tr>
          {rows_html}
        </table>"""

    return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#222">
      <h2 style="border-bottom:2px solid #2d6a4f;padding-bottom:8px">
        {subject_line}
      </h2>

      <p style="font-size:15px">
        <strong>{len(ok)}/{len(results)}</strong> councils scraped successfully &nbsp;│&nbsp;
        <strong>{total:,}</strong> total sites &nbsp;│&nbsp;
        <strong style="color:#2d6a4f">{len(new_props)} new</strong> &nbsp;│&nbsp;
        <strong style="color:#c0392b">{len(removed_props)} removed</strong>
      </p>

      <h3 style="color:#333">📋 Council Status</h3>
      <table style="border-collapse:collapse;width:100%;font-size:13px">
        <tr style="background:#f5f5f5;font-weight:bold">
          <th style="padding:4px 8px;text-align:left">Council</th>
          <th style="padding:4px 8px;text-align:left">Status</th>
          <th style="padding:4px 8px;text-align:left">Detail</th>
        </tr>
        {council_rows}
      </table>

      {new_section}
      {removed_section}

      <p style="font-size:11px;color:#999;margin-top:32px;border-top:1px solid #eee;padding-top:12px">
        Sent by Revive Ireland nightly scraper · {run_date}
      </p>
    </body>
    </html>
    """


def send(results: list, run_date: str = None) -> None:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        print("RESEND_API_KEY not set — skipping email notification")
        return

    if not run_date:
        run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    successful_councils = [r["code"] for r in results if r["status"] == "ok"]
    changes = database.get_changes_since(run_date, successful_councils)
    new_props     = changes["new"]
    removed_props = changes["removed"]

    ok     = [r for r in results if r["status"] == "ok"]
    errors = [r for r in results if r["status"] != "ok"]
    status = "✅" if not errors else "⚠️"
    subject = f"{status} Revive Ireland — {run_date} · {len(ok)}/{len(results)} councils · {len(new_props)} new"

    html = _build_html(run_date, results, new_props, removed_props)

    resp = requests.post(
        _RESEND_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from":    _FROM_ADDRESS,
            "to":      [_TO_ADDRESS],
            "subject": subject,
            "html":    html,
        },
        timeout=15,
    )
    resp.raise_for_status()
    print(f"Digest email sent → {_TO_ADDRESS} (id: {resp.json().get('id')})")
