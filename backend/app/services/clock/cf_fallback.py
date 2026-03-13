"""
Cloudflare Pages Static Fallback — deploy a snapshot of current clock scores.

Runs every hour via APScheduler. If the main backend goes down, the static
page on Cloudflare Pages shows the last known Doomsday Clock scores.

Flow:
  1. Fetch all country scores from DB
  2. Render a minimal HTML page with the data embedded as JSON
  3. Push to Cloudflare Pages via Direct Upload API
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ── Cloudflare API helpers ────────────────────────────────────────────────────

CF_API_BASE = "https://api.cloudflare.com/client/v4"


async def _get_cf_credentials() -> tuple[str, str, str] | None:
    """Return (api_token, account_id, project_name) or None if not configured."""
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    project = os.getenv("CLOUDFLARE_PAGES_PROJECT", "doomsday-fallback")
    if not token or not account:
        logger.warning("Cloudflare credentials not configured — skipping CF Pages deploy")
        return None
    return token, account, project


async def _upload_to_cf_pages(
    html_content: str,
    api_token: str,
    account_id: str,
    project_name: str,
) -> bool:
    """Upload a single index.html to Cloudflare Pages via Direct Upload."""
    url = f"{CF_API_BASE}/accounts/{account_id}/pages/projects/{project_name}/deployments"

    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / "index.html"
        index_path.write_text(html_content, encoding="utf-8")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                with open(index_path, "rb") as f:
                    response = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {api_token}"},
                        files={"index.html": ("index.html", f, "text/html")},
                    )

            if response.status_code in (200, 201):
                data = response.json()
                deploy_url = data.get("result", {}).get("url", "unknown")
                logger.info("CF Pages deploy success: %s", deploy_url)
                return True
            else:
                logger.error(
                    "CF Pages deploy failed: HTTP %s — %s",
                    response.status_code,
                    response.text[:200],
                )
                return False

        except httpx.RequestError as exc:
            logger.error("CF Pages deploy request error: %s", exc)
            return False


# ── HTML generation ───────────────────────────────────────────────────────────

def _build_fallback_html(scores: list[dict[str, Any]], generated_at: str) -> str:
    """Render a self-contained HTML fallback page with embedded JSON data."""
    scores_json = json.dumps(scores, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Doomsday Clock — Offline Fallback</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#0a0a0a;color:#e5e5e5;font-family:system-ui,sans-serif;padding:2rem}}
    h1{{font-size:1.5rem;font-weight:700;margin-bottom:.5rem}}
    .notice{{background:#1a1a1a;border:1px solid #333;border-radius:.5rem;padding:1rem;margin-bottom:2rem;font-size:.875rem;color:#888}}
    .notice strong{{color:#e5e5e5}}
    table{{width:100%;border-collapse:collapse;font-size:.875rem}}
    th{{text-align:left;padding:.5rem .75rem;border-bottom:1px solid #222;color:#888;font-weight:500}}
    td{{padding:.5rem .75rem;border-bottom:1px solid #111}}
    .risk-green{{color:#22c55e}}
    .risk-yellow{{color:#eab308}}
    .risk-orange{{color:#f97316}}
    .risk-red{{color:#ef4444}}
  </style>
</head>
<body>
  <h1>Doomsday Clock</h1>
  <div class="notice">
    <strong>You are viewing a cached snapshot.</strong>
    The live site is temporarily unavailable. Last updated: {generated_at}
  </div>
  <table id="scores-table">
    <thead>
      <tr>
        <th>Country</th>
        <th>Seconds to Midnight</th>
        <th>Risk Level</th>
        <th>Updated</th>
      </tr>
    </thead>
    <tbody id="scores-body"></tbody>
  </table>
  <script>
    const scores = {scores_json};
    const tbody = document.getElementById('scores-body');
    const riskClass = (level) => {{
      const map = {{green:'risk-green',yellow:'risk-yellow',orange:'risk-orange',red:'risk-red'}};
      return map[level] || '';
    }};
    scores.sort((a,b)=>a.seconds_to_midnight - b.seconds_to_midnight).forEach(s=>{{
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${{s.country_name}} (${{s.country_code}})</td>
        <td>${{s.seconds_to_midnight.toFixed(1)}}s</td>
        <td class="${{riskClass(s.risk_level)}}">${{s.risk_level}}</td>
        <td>${{new Date(s.updated_at).toLocaleString()}}</td>
      `;
      tbody.appendChild(tr);
    }});
  </script>
</body>
</html>"""


# ── Main entry point called by scheduler ─────────────────────────────────────

async def deploy_static_fallback() -> None:
    """
    Build and deploy the static fallback page to Cloudflare Pages.
    Called every hour by APScheduler.
    """
    creds = await _get_cf_credentials()
    if creds is None:
        return  # Credentials not configured, skip silently

    api_token, account_id, project_name = creds

    # Import DB only when needed (avoids circular imports at module load)
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.clock import CountryRiskScore
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CountryRiskScore).order_by(CountryRiskScore.seconds_to_midnight)
            )
            rows = result.scalars().all()

        scores = [
            {
                "country_code": r.country_code,
                "country_name": r.country_name,
                "seconds_to_midnight": r.seconds_to_midnight,
                "risk_level": r.risk_level,
                "updated_at": r.updated_at.isoformat() if r.updated_at else "",
            }
            for r in rows
        ]

    except Exception as exc:
        logger.error("CF fallback: failed to fetch scores from DB: %s", exc)
        scores = []

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = _build_fallback_html(scores, generated_at)

    await _upload_to_cf_pages(html, api_token, account_id, project_name)
