"""Input validation utilities to prevent path traversal and injection."""

import re

_SAFE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def validate_safe_id(value: str, field_name: str = "id") -> str:
    """Validate that a string is safe for use as a file path component.

    Raises ValueError if the value contains path traversal or unsafe characters.
    """
    if not value or not isinstance(value, str):
        raise ValueError(f"{field_name} must be a non-empty string")
    if not _SAFE_ID_PATTERN.match(value):
        raise ValueError(f"{field_name} contains invalid characters")
    if len(value) > 256:
        raise ValueError(f"{field_name} exceeds maximum length")
    return value
