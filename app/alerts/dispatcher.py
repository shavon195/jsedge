"""
JSEdge - Alert dispatcher.

Decides what alerts to fire, on which channel, and logs every send
to alerts_log so we never double-send the same event.

Public functions:
    check_target_hits()      - scan watchlist, fire alerts for any
                               target that just became hit
    send_keep_alive()        - fire the WhatsApp 'good morning'
                               keep-alive if 48+ hours since last
                               WhatsApp message
    log_alert(...)           - internal: record a send in alerts_log

Each function returns a dict describing what happened so a daily
cron script can print a summary.
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Optional

from app.alerts.email import send_email
from app.alerts.whatsapp import send_whatsapp
from app.database import get_connection
from app.watchlist import list_watchlist

log = logging.getLogger(__name__)

# How fresh a previous target_hit alert has to be to suppress a re-fire.
# If we sent a target_hit alert for CAR within the last 7 days and the
# price is still hitting target, we don't re-spam. This protects against
# the "stock hovers around target for a week" scenario.
TARGET_HIT_COOLDOWN_HOURS = 24 * 7

# Keep-alive cadence: send 'good morning' if the most recent outbound
# WhatsApp message was 48+ hours ago. Twilio's window closes at 72.
KEEP_ALIVE_THRESHOLD_HOURS = 48

# Placeholder verse list — swap with Shavon's curated list later.
KEEP_ALIVE_VERSES = [
    ("For I know the plans I have for you, declares the Lord, plans to "
     "prosper you and not to harm you, plans to give you hope and a future.",
     "Jeremiah 29:11"),
    ("Trust in the Lord with all your heart, and lean not on your own "
     "understanding.",
     "Proverbs 3:5"),
    ("I can do all things through Christ who strengthens me.",
     "Philippians 4:13"),
    ("The Lord is my shepherd; I shall not want.",
     "Psalm 23:1"),
    ("Be still, and know that I am God.",
     "Psalm 46:10"),
    ("And we know that in all things God works for the good of those who "
     "love him, who have been called according to his purpose.",
     "Romans 8:28"),
    ("Cast all your anxiety on him because he cares for you.",
     "1 Peter 5:7"),
]

KEEP_ALIVE_GREETINGS = [
    "Good morning, Shavon!",
    "Blessings on your day, Shavon!",
    "Peace be with you, Shavon!",
    "Good morning! Hope today brings you joy.",
]


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------
def log_alert(
    alert_type:      str,
    message_summary: str,
    delivered_via:   str,
    stock_id:        Optional[int] = None,
) -> None:
    """Record a successful (or failed) alert send in alerts_log."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO alerts_log (stock_id, alert_type, message_summary, delivered_via) "
            "VALUES (?, ?, ?, ?)",
            (stock_id, alert_type, message_summary[:500], delivered_via),
        )
        conn.commit()
    finally:
        conn.close()


def _recently_alerted(stock_id: int, alert_type: str, hours: int) -> bool:
    """True if we sent an alert of this type for this stock within `hours`."""
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM alerts_log "
            "WHERE stock_id = ? AND alert_type = ? AND sent_at > ? "
            "AND delivered_via != 'failed' "
            "LIMIT 1",
            (stock_id, alert_type, cutoff),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _hours_since_last_whatsapp() -> Optional[float]:
    """How many hours since we last successfully sent ANY WhatsApp message.

    Returns None if we've never sent one (cold start).
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT sent_at FROM alerts_log "
            "WHERE delivered_via IN ('whatsapp', 'both') "
            "AND delivered_via != 'failed' "
            "ORDER BY sent_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    last = datetime.strptime(row["sent_at"], "%Y-%m-%d %H:%M:%S")
    return (datetime.utcnow() - last).total_seconds() / 3600.0


# ---------------------------------------------------------------------------
# Target-hit alerts
# ---------------------------------------------------------------------------
def check_target_hits() -> dict:
    """
    Scan the watchlist for stocks where the current price has hit
    the target. Fire alerts (email + WhatsApp) for any new hits.

    Returns:
        {
            "checked":   <int>,    # total active watchlist rows examined
            "new_hits":  [...],    # list of symbols newly alerted
            "skipped":   [...],    # list of {symbol, reason} for hits that
                                   # weren't re-alerted (cooldown, etc.)
            "errors":    [...],    # any send failures
        }
    """
    actives = list_watchlist(state="active")
    result = {"checked": len(actives), "new_hits": [], "skipped": [], "errors": []}

    for w in actives:
        if w["gap_state"] != "hit":
            continue

        if _recently_alerted(w["stock_id"], "target_hit", TARGET_HIT_COOLDOWN_HOURS):
            result["skipped"].append({
                "symbol": w["symbol"],
                "reason": "alerted in last 7 days",
            })
            continue

        # Build alert content.
        subject = f"JSEdge - target hit: {w['symbol']} @ ${w['current_price']:.2f}"
        body_text = (
            f"*{w['symbol']}* hit your target of ${w['limit_price']:.2f}.\n"
            f"Current price: ${w['current_price']:.2f}\n"
            f"({w['name']})"
        )
        if w["notes"]:
            body_text += f"\n\nYour note: \"{w['notes']}\""

        html_body = (
            f"<h2>{w['symbol']} hit your target!</h2>"
            f"<p><strong>{w['name']}</strong></p>"
            f"<p>Target: <strong>${w['limit_price']:.2f}</strong><br>"
            f"Current: <strong>${w['current_price']:.2f}</strong></p>"
        )
        if w["notes"]:
            html_body += f"<p style='color:#64748b'>Your note: \"{w['notes']}\"</p>"
        html_body += (
            "<p style='color:#64748b;font-size:12px;margin-top:24px;'>"
            "Sent by JSEdge from your watchlist.</p>"
        )

        # Send via both channels.
        email_result = send_email(subject, html_body)
        wa_result    = send_whatsapp(body_text)

        if email_result["ok"] and wa_result["ok"]:
            delivered = "both"
        elif email_result["ok"]:
            delivered = "email"
        elif wa_result["ok"]:
            delivered = "whatsapp"
        else:
            delivered = "failed"
            result["errors"].append({
                "symbol": w["symbol"],
                "email_err": email_result.get("error"),
                "wa_err":    wa_result.get("error"),
            })

        log_alert(
            alert_type      = "target_hit",
            message_summary = f"{w['symbol']} hit ${w['limit_price']:.2f} (current ${w['current_price']:.2f})",
            delivered_via   = delivered,
            stock_id        = w["stock_id"],
        )

        if delivered != "failed":
            result["new_hits"].append({
                "symbol":    w["symbol"],
                "delivered": delivered,
            })

    return result


# ---------------------------------------------------------------------------
# Keep-alive ping
# ---------------------------------------------------------------------------
def send_keep_alive(force: bool = False) -> dict:
    """
    Send a friendly 'good morning' WhatsApp if 48+ hours have passed
    since our last outbound WhatsApp message. Keeps Twilio's 72-hour
    sandbox window from closing.

    Set force=True to send unconditionally (useful for testing).

    Returns:
        {"sent": True,  "hours_since_last": <float|None>}
        {"sent": False, "reason": "<why>"}
    """
    hours = _hours_since_last_whatsapp()

    if not force:
        if hours is not None and hours < KEEP_ALIVE_THRESHOLD_HOURS:
            return {
                "sent": False,
                "reason": f"only {hours:.1f}h since last WhatsApp "
                          f"(threshold {KEEP_ALIVE_THRESHOLD_HOURS}h)",
            }

    greeting       = random.choice(KEEP_ALIVE_GREETINGS)
    verse_text, ref = random.choice(KEEP_ALIVE_VERSES)

    body = (
        f"{greeting} 🌅\n\n"
        f"\"{verse_text}\"\n— {ref}\n\n"
        f"A gentle reminder to drop me a quick reply so JSEdge "
        f"can keep watching your stocks. Have a blessed day. 🙏"
    )

    wa_result = send_whatsapp(body)
    delivered = "whatsapp" if wa_result["ok"] else "failed"

    log_alert(
        alert_type      = "keep_alive",
        message_summary = f"keep-alive: {ref}",
        delivered_via   = delivered,
        stock_id        = None,
    )

    return {
        "sent":             wa_result["ok"],
        "hours_since_last": hours,
        "verse_ref":        ref,
        "error":            wa_result.get("error") if not wa_result["ok"] else None,
    }