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

from openai import OpenAI

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # cheap and solid for this task
BATCH_SIZE = 40  # items per API call, keeps each request small and predictable

SYSTEM_PROMPT = (
    "You clean up raw Discord messages for a daily digest. For each numbered "
    "item: fix grammar/typos, translate to clear English if it isn't already, "
    "and tighten wording. Do not add facts, links, or details that aren't in "
    "the original text. Do not editorialize or add commentary. Keep each "
    "result close to the original length. "
    'Respond ONLY with JSON in this exact shape: '
    '{"items": [{"index": 0, "text": "..."}, ...]}, one entry per input item, '
    "using the same indices you were given."
)


def _clean_batch(client, batch):
    """batch is a list of (index, entry_dict) tuples. Returns {index: cleaned_text}."""
    payload = [{"index": i, "text": entry["content"]} for i, entry in batch]
    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    result = json.loads(response.choices[0].message.content)
    return {item["index"]: item["text"] for item in result.get("items", [])}


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

    for start in range(0, len(indexed), BATCH_SIZE):
        batch = indexed[start:start + BATCH_SIZE]
        try:
            cleaned = _clean_batch(client, batch)
        except Exception as exc:
            print(f"AI cleanup failed for a batch, keeping raw text for it: {exc}")
            continue
        for i, entry in batch:
            text = cleaned.get(i, "").strip()
            if text:
                entry["content"] = text

    return grouped
