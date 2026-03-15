"""
Prompt Injection defense — Layer 1: Input Sanitizer.

Filters known injection patterns, token boundaries, HTML tags, and
base64-encoded commands from text before it enters LLM context.
Designed to sanitize web search results (e.g. from Tavily API).
"""

import re
from typing import Any

# ---------------------------------------------------------------------------
# Injection patterns (case-insensitive)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?previous\s+instructions?",
        r"system\s+prompt",
        r"you\s+are\s+now",
        r"act\s+as\s+(if\s+you\s+are\s+)?",
        r"pretend\s+(you\s+are|to\s+be)",
        r"disregard\s+(all\s+)?previous",
        r"forget\s+(all\s+)?previous",
        r"override\s+(all\s+)?instructions?",
        r"new\s+instructions?\s*:",
        r"jailbreak",
        r"DAN\s+mode",
    ]
]

# ---------------------------------------------------------------------------
# Token boundary markers
# ---------------------------------------------------------------------------

_TOKEN_BOUNDARIES: list[str] = [
    "<|im_start|>",
    "<|im_end|>",
    "<|endoftext|>",
    "[INST]",
    "[/INST]",
]

# ---------------------------------------------------------------------------
# HTML / script patterns
# ---------------------------------------------------------------------------

_HTML_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"<script[\s>].*?</script>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<style[\s>].*?</style>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<iframe[\s>].*?</iframe>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<!--.*?-->", re.DOTALL),
    # Self-closing / unclosed variants
    re.compile(r"<script[^>]*/?>", re.IGNORECASE),
    re.compile(r"<style[^>]*/?>", re.IGNORECASE),
    re.compile(r"<iframe[^>]*/?>", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Base64 data-URI pattern
# ---------------------------------------------------------------------------

_BASE64_PATTERN = re.compile(
    r"data:[a-zA-Z0-9/+\-]+;base64,[A-Za-z0-9+/=]+", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

TRUNCATION_SUFFIX = "...[truncated]"


def sanitize_text(text: str, max_length: int = 2000) -> str:
    """Sanitize a single text string.

    - Removes known prompt injection patterns
    - Removes LLM token boundary markers
    - Removes dangerous HTML tags and comments
    - Removes base64-encoded data URIs
    - Truncates to *max_length* characters

    Matched patterns are replaced with ``[FILTERED]``.
    """
    if not text:
        return text

    # 1. Injection patterns
    for pat in _INJECTION_PATTERNS:
        text = pat.sub("[FILTERED]", text)

    # 2. Token boundaries (literal string replacement)
    for marker in _TOKEN_BOUNDARIES:
        text = text.replace(marker, "[FILTERED]")

    # 3. HTML / script tags
    for pat in _HTML_PATTERNS:
        text = pat.sub("[FILTERED]", text)

    # 4. Base64 data URIs
    text = _BASE64_PATTERN.sub("[FILTERED]", text)

    # 5. Truncate
    if len(text) > max_length:
        text = text[: max_length - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX

    return text


def sanitize_search_results(
    results: list[dict[str, Any]],
    max_per_result: int = 2000,
    max_total: int = 10000,
) -> list[dict[str, Any]]:
    """Sanitize a list of search-result dicts.

    Each dict is expected to have at least ``content``; ``title`` and ``url``
    are preserved as-is.  The ``content`` field is sanitized and truncated
    to *max_per_result*.  The total content across all results is capped at
    *max_total*.
    """
    sanitized: list[dict[str, Any]] = []
    total_len = 0

    for item in results:
        entry = dict(item)  # shallow copy
        content = entry.get("content", "")

        # Per-result sanitize + truncate
        content = sanitize_text(content, max_length=max_per_result)

        # Enforce global budget
        remaining = max_total - total_len
        if remaining <= 0:
            break
        if len(content) > remaining:
            content = content[: remaining - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX

        entry["content"] = content
        total_len += len(content)
        sanitized.append(entry)

    return sanitized
