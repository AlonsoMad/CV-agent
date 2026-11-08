"""Deterministic extraction of recruiter emails and LinkedIn URLs from posting text.

Everything here is pure: no I/O, no clock, no randomness. It runs inside an
activity, so it must be safe to replay.
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

LINKEDIN_RE = re.compile(
    r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:in|jobs|company)/[A-Za-z0-9\-_%./?=&]+",
    re.IGNORECASE,
)

# Matches that are really asset filenames rather than contact addresses.
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp")

# Local parts that never reach a human.
_REJECTED_LOCAL_PARTS = ("noreply", "no-reply", "donotreply", "do-not-reply")

# Domains reserved for documentation/examples; never a real recruiter.
_REJECTED_DOMAINS = ("example.com", "example.org", "example.net")

_TRAILING_PUNCTUATION = ".,;:!?)]}>\"'"

# Lower number wins when several LinkedIn URLs are present: a job posting beats
# a company page, which beats a bare profile, because the ask is "a LinkedIn
# profile for the opening or its recruiter".
_LINKEDIN_KIND_PRIORITY = {"jobs": 0, "in": 1, "company": 2}


def extract_email(text: str) -> str:
    """Return the first plausible contact email in ``text``, or ``""``."""
    for match in EMAIL_RE.finditer(text or ""):
        candidate = match.group(0).rstrip(_TRAILING_PUNCTUATION).lower()
        if candidate.endswith(_IMAGE_EXTENSIONS):
            continue
        local_part, _, domain = candidate.partition("@")
        if not local_part or not domain:
            continue
        if local_part in _REJECTED_LOCAL_PARTS:
            continue
        if domain in _REJECTED_DOMAINS:
            continue
        return candidate
    return ""


def normalize_linkedin(url: str) -> str:
    """Strip query/fragment, force https, and keep only a known LinkedIn path.

    Returns ``""`` for anything that is not a LinkedIn ``/in``, ``/jobs`` or
    ``/company`` URL.
    """
    if not url:
        return ""
    match = LINKEDIN_RE.search(url.strip())
    if match is None:
        return ""
    cleaned = match.group(0).split("?", 1)[0].split("#", 1)[0]
    cleaned = re.sub(r"^https?://", "https://", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^https://(?:[a-z]{2,3}\.)?linkedin\.com",
        "https://www.linkedin.com",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.rstrip(_TRAILING_PUNCTUATION).rstrip("/")


def _linkedin_kind(url: str) -> int:
    for kind, priority in _LINKEDIN_KIND_PRIORITY.items():
        if f"/{kind}/" in url:
            return priority
    return len(_LINKEDIN_KIND_PRIORITY)


def extract_linkedin(text: str) -> str:
    """Return the most useful LinkedIn URL in ``text``, or ``""``.

    Preference order: job posting, then profile, then company page. Ties are
    broken by first appearance so the result is stable.
    """
    best = ""
    best_key: tuple[int, int] | None = None
    for index, match in enumerate(LINKEDIN_RE.finditer(text or "")):
        normalized = normalize_linkedin(match.group(0))
        if not normalized:
            continue
        key = (_linkedin_kind(normalized), index)
        if best_key is None or key < best_key:
            best, best_key = normalized, key
    return best


def contact_kind(contact_email: str, linkedin_url: str, source_url: str) -> str:
    """Classify where a consumer should go to act on an opening."""
    if contact_email:
        return "email"
    if linkedin_url:
        return "linkedin"
    if source_url:
        return "url"
    return "none"
