"""Parse JSON from raw LLM output for extractors without native structured output.

Used by LocalExtractor and any future text-based extractors that rely on
prompt-based JSON instead of schema-constrained APIs.
"""

from __future__ import annotations

import json
import re


def extract_json_object(raw: str) -> dict | None:
    """Extract a single JSON object from raw model output.

    Strips markdown code fences (e.g. ```json ... ```) if present, then
    finds the outermost { ... } and parses it. Returns the parsed dict,
    or None if no valid JSON object could be found or parsing failed.
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip()

    # Strip markdown code fence: ```json ... ``` or ``` ... ```
    fence = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)
    match = fence.search(text)
    if match:
        text = match.group(1).strip()

    # Find the first { and then match braces to get the outermost object
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    quote_char = None
    end = -1

    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if not in_string:
            if c in ("'", '"'):
                in_string = True
                quote_char = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        else:
            if c == quote_char:
                in_string = False

    if end == -1:
        return None

    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
