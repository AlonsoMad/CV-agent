"""Deterministic serialization of job openings to CSV and JSON."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone

from pydantic import ValidationError

from .contacts import contact_kind, extract_email, extract_linkedin, normalize_linkedin
from .models import JobOpening, JobSearchOutput

CSV_COLUMNS = [
    "opening_id",
    "position",
    "company",
    "location",
    "description",
    "validation_criteria",
    "match_score",
    "contact_kind",
    "source_url",
    "contact_email",
    "linkedin_url",
    "source",
    "found_at",
]

SCHEMA_VERSION = "1"


def parse_openings(raw: str) -> list[JobOpening]:
    """Parse a (possibly noisy) LLM response into validated JobOpening rows."""
    openings: list[JobOpening] = []
    for item in _extract_json_array(raw):
        if not isinstance(item, dict):
            continue
        try:
            openings.append(JobOpening.model_validate(item))
        except ValidationError:
            continue
    return openings


def build_output(cv_variant: str, openings: list[JobOpening], max_openings: int) -> JobSearchOutput:
    """Enrich with contact data, deduplicate, rank, and serialize openings."""
    ranked = sorted(openings, key=lambda o: o.match_score, reverse=True)

    seen_keys: set[tuple[str, str]] = set()
    seen_urls: set[str] = set()
    unique: list[JobOpening] = []
    for opening in ranked:
        key = (opening.position.strip().lower(), opening.company.strip().lower())
        url = normalize_source_url(opening.source_url)
        if key in seen_keys or (url and url in seen_urls):
            continue
        seen_keys.add(key)
        if url:
            seen_urls.add(url)
        unique.append(opening)

    unique = unique[:max_openings]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for opening in unique:
        enrich_contacts(opening)
        if not opening.found_at:
            opening.found_at = today
        opening.opening_id = compute_opening_id(opening)

    return JobSearchOutput(
        schema_version=SCHEMA_VERSION,
        cv_variant=cv_variant,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        count=len(unique),
        openings=unique,
        csv=to_csv(unique),
    )


def enrich_contacts(opening: JobOpening) -> None:
    """Fill blank contact fields from the posting text; never overwrite the model.

    The model's own values win because it saw the page; extraction only fills
    blanks and normalizes whatever LinkedIn URL ends up on the row.
    """
    haystack = f"{opening.description} {opening.source_url} {opening.validation_criteria}"
    if not opening.contact_email:
        opening.contact_email = extract_email(haystack)
    if not opening.linkedin_url:
        opening.linkedin_url = extract_linkedin(haystack)
    else:
        opening.linkedin_url = normalize_linkedin(opening.linkedin_url)
    opening.contact_kind = contact_kind(
        opening.contact_email, opening.linkedin_url, opening.source_url
    )


def normalize_source_url(url: str) -> str:
    """Normalize a posting URL for dedupe and stable ids."""
    cleaned = (url or "").strip().split("#", 1)[0]
    return cleaned.rstrip("/").lower()


def compute_opening_id(opening: JobOpening) -> str:
    """Stable id so a downstream agent can dedupe across runs."""
    basis = "|".join(
        (
            opening.position.strip().lower(),
            opening.company.strip().lower(),
            normalize_source_url(opening.source_url),
        )
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def to_csv(openings: list[JobOpening]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for opening in openings:
        writer.writerow({column: getattr(opening, column) for column in CSV_COLUMNS})
    return buffer.getvalue()


def _extract_json_array(raw: str) -> list:
    text = raw.strip()
    for candidate in re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL):
        try:
            value = json.loads(candidate.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            return value
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
        if isinstance(value, list):
            return value
    return []
