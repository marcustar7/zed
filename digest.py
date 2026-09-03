"""
Builds the daily report: a short text summary (for the DM body) and a
full PDF attachment, then sends both to every configured recipient.
"""

from datetime import datetime, timezone
from collections import defaultdict

import discord
from fpdf import FPDF

from storage import get_unsent_items, mark_all_sent
from ai_cleanup import clean_and_translate

CATEGORY_LABELS = {
    "announcements": "Announcements",
    "news": "News",
    "events": "Events",
    "livestreams": "Livestreams",
}


def _safe(text: str) -> str:
    """fpdf2's default font only supports latin-1. Normalize common 'smart'
    punctuation to plain ASCII first, so quotes/dashes don't get mangled into
    literal '?' characters, then fall back safely for anything else."""
    replacements = {
        "\u2018": "'", "\u2019": "'",    # smart single quotes
        "\u201c": '"', "\u201d": '"',    # smart double quotes
        "\u2013": "-", "\u2014": "--",   # en dash, em dash
        "\u2026": "...",                  # ellipsis
        "\u00a0": " ",                     # non-breaking space
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", "replace").decode("latin-1")


def _parse_event_date(date_str):
    """Parses an AI-resolved 'YYYY-MM-DD' string into a date object, or None
    if missing/null/malformed."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def build_report():
    """Returns (summary_text, pdf_filename, item_ids) or (None, None, []) if nothing new."""
    items = get_unsent_items()
    if not items:
        return None, None, []

    grouped = {}
    ids = []
    for (item_id, guild_name, channel_name, category, author, content, url, created_at) in items:
        ids.append(item_id)
        grouped.setdefault(category, []).append(
            {
                "guild": guild_name,
                "channel": channel_name,
                "author": author,
                "content": content,
                "url": url,
            }
        )

    grouped = clean_and_translate(grouped)

    # Pull anything with an AI-resolved date into a single chronological
    # timeline, spanning every category/channel/server together.
    dated = defaultdict(list)
    for entries in grouped.values():
        for e in entries:
            d = _parse_event_date(e.get("event_date"))
            if d:
                dated[d].append(e)
    sorted_dates = sorted(dated.keys())

    # ---- short summary for the DM body ----
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    lines = [f"**Daily Report — {today}**"]

    if sorted_dates:
        lines.append("\n📅 **Coming Up**")
        for d in sorted_dates:
            lines.append(f"\n{d.strftime('%A, %b %d')}")
            for e in dated[d]:
                snippet = e["content"][:220] + ("…" if len(e["content"]) > 220 else "")
                line = f"• [{e['guild']}/{e['channel']}]: {snippet}"
                if e["url"]:
                    line += f"\n   <{e['url']}>"
                lines.append(line)

    for category, label in CATEGORY_LABELS.items():
        entries = grouped.get(category)
        if not entries:
            continue
        lines.append(f"\n**{label}** ({len(entries)})")
        for e in entries[:5]:
            snippet = e["content"][:220] + ("…" if len(e["content"]) > 220 else "")
            line = f"• [{e['guild']}/{e['channel']}] {e['author']}: {snippet}"
            if e["url"]:
                # Angle brackets suppress Discord's link preview/embed, keeping a
                # digest with many items compact instead of spawning previews for each.
                line += f"\n   <{e['url']}>"
            lines.append(line)
        if len(entries) > 5:
            lines.append(f"…and {len(entries) - 5} more — see attached PDF")
    summary_text = "\n".join(lines)

    # ---- full PDF ----
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _safe(f"Daily Report - {today}"), ln=True)

    if sorted_dates:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, _safe("Coming Up"), ln=True)
        for d in sorted_dates:
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 7, _safe(d.strftime("%A, %B %d, %Y")), ln=True)
            pdf.set_font("Helvetica", "", 10)
            for e in dated[d]:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, _safe(f"[{e['guild']} / {e['channel']}]: {e['content']}"))
                if e["url"]:
                    pdf.set_x(pdf.l_margin)
                    pdf.set_text_color(0, 0, 255)
                    pdf.multi_cell(0, 6, _safe(e["url"]))
                    pdf.set_text_color(0, 0, 0)
                pdf.ln(1)

    for category, label in CATEGORY_LABELS.items():
        entries = grouped.get(category)
        if not entries:
            continue
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, _safe(label), ln=True)
        pdf.set_font("Helvetica", "", 10)
        for e in entries:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6, _safe(f"[{e['guild']} / {e['channel']}] {e['author']}: {e['content']}"))
            if e["url"]:
                pdf.set_x(pdf.l_margin)
                pdf.set_text_color(0, 0, 255)
                pdf.multi_cell(0, 6, _safe(e["url"]))
                pdf.set_text_color(0, 0, 0)
            pdf.ln(1)

    filename = f"report_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    pdf.output(filename)

    return summary_text, filename, ids


async def send_daily_report(bot, recipient_ids):
    """Returns True if a report was sent, False if there was nothing new to report."""
    summary_text, filename, ids = build_report()
    if summary_text is None:
        return False  # nothing new since the last report

    for user_id in recipient_ids:
        try:
            user = await bot.fetch_user(int(user_id))
            await user.send(content=summary_text[:1900], file=discord.File(filename))
        except Exception as exc:
            print(f"Could not DM user {user_id}: {exc}")

    mark_all_sent(ids)
    return True