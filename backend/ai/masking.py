"""Mask sensitive data before it reaches the LLM (requirement 11.1).

Applied to free-text the user feeds into agentic prompts (briefs, guidance,
descriptions). Deterministic and reversible-free — it simply redacts.
"""

from __future__ import annotations

import re

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE = re.compile(r"\b\+?\d[\d\s().-]{7,}\d\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def mask_pii(text: str | None) -> str:
    if not text:
        return text or ""
    text = _EMAIL.sub("[email]", text)
    text = _SSN.sub("[id]", text)
    text = _PHONE.sub("[phone]", text)
    return text
