"""
Optional AI cleanup pass. Sends each day's raw captured text to OpenAI and
asks it to fix grammar/typos and translate non-English text to English,
without inventing anything not present in the original.

This only ever touches the copy of the text used to build that day's report
-- the raw, unedited version stays in reports.db untouched.

If OPENAI_API_KEY isn't set, or the API call fails for any reason, cleanup
is silently skipped and the report falls back to the raw text. A bad or
missing API key should never block the daily digest from going out.
"""

import os
import json
from datetime import datetime, timezone

from openai import OpenAI

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # cheap and solid for this task
BATCH_SIZE = 40  # items per API call, keeps each request small and predictable

SYSTEM_PROMPT_TEMPLATE = (
    "Today's date is {today}. You prepare raw Discord messages for a scannable "
    "daily digest. For each numbered item: translate to clear English if it "
    "isn't already, fix grammar/typos, and condense it into a tight 1-2 "
    "sentence summary that captures the key point. A short message can just "
    "be cleaned up as-is without being forced shorter. Do not add facts, "
    "links, or details that aren't in the original text, and do not "
    "editorialize or add commentary beyond what's stated.\n\n"
    "Additionally, if a message references or implies a specific date or "
    "timeframe (e.g. 'this Friday', 'next week', 'Sept 10th', 'tonight', "
    "'dropping this weekend'), resolve it to an absolute calendar date in "
    "YYYY-MM-DD format, using today's date as the reference point. If there's "
    "no date reference at all, use null for that item's date. For an "
    "ambiguous multi-day range like 'this weekend', resolve to the first day "
    "of that range.\n\n"
    'Respond ONLY with JSON in this exact shape: '
    '{{"items": [{{"index": 0, "text": "...", "date": "YYYY-MM-DD or null"}}, ...]}}, '
    "one entry per input item, using the same indices you were given."
)


def _clean_batch(client, batch, today_str):
    """batch is a list of (index, entry_dict) tuples. Returns {index: {"text":..., "date":...}}."""
    payload = [{"index": i, "text": entry["content"]} for i, entry in batch]
    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE.format(today=today_str)},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    result = json.loads(response.choices[0].message.content)
    return {item["index"]: item for item in result.get("items", [])}


def clean_and_translate(grouped: dict) -> dict:
    """
    grouped: {category: [ {guild, channel, author, content, url}, ... ]}
    Mutates entries' "content" in place where cleanup succeeds, and returns
    the same dict either way.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set - skipping AI cleanup, using raw text.")
        return grouped

    flat = [entry for entries in grouped.values() for entry in entries]
    if not flat:
        return grouped

    client = OpenAI(api_key=api_key)
    indexed = list(enumerate(flat))
    today_str = datetime.now(timezone.utc).date().isoformat()

    for start in range(0, len(indexed), BATCH_SIZE):
        batch = indexed[start:start + BATCH_SIZE]
        try:
            cleaned = _clean_batch(client, batch, today_str)
        except Exception as exc:
            print(f"AI cleanup failed for a batch, keeping raw text for it: {exc}")
            continue
        for i, entry in batch:
            item = cleaned.get(i)
            if not item:
                continue
            text = (item.get("text") or "").strip()
            if text:
                entry["content"] = text
            entry["event_date"] = item.get("date")  # None/null if no date reference

    return grouped
