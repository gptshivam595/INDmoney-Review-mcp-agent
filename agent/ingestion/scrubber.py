from __future__ import annotations

import re

from agent.ingestion.common import normalize_text

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)")
AADHAAR_RE = re.compile(r"(?<!\d)\d{4}[-\s]?\d{4}[-\s]?\d{4}(?!\d)")


def scrub_pii(text: str) -> str:
    scrubbed = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    scrubbed = PHONE_RE.sub("[REDACTED_PHONE]", scrubbed)
    scrubbed = AADHAAR_RE.sub("[REDACTED_AADHAAR]", scrubbed)
    return normalize_text(scrubbed)

