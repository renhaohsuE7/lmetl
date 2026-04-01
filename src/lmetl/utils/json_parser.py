"""Robust JSON parsing for LLM-generated output."""

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def parse_llm_json(raw: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Parse JSON from LLM output, handling common issues.

    Returns:
        (parsed_dict, error_message) — error_message is None on success.
    """
    content = raw.strip()

    # Strip markdown code fences
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first line (```json or ```) and last line (```)
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines)

    # Try direct parse first
    try:
        return json.loads(content), None
    except json.JSONDecodeError:
        pass

    # Clean up common LLM JSON issues
    cleaned = _clean_json(content)
    try:
        return json.loads(cleaned), None
    except json.JSONDecodeError as e:
        logger.warning("JSON parse failed after cleanup: %s", e)
        return None, str(e)


def _clean_json(text: str) -> str:
    """Fix common JSON issues from LLM output."""
    # Remove control characters (except \n, \t, \r which are valid in strings)
    # Replace invalid control chars with space
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', text)

    # Fix trailing commas before ] or }
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)

    # Fix duplicate keys with same value (just leave them, json.loads takes last)
    return cleaned
