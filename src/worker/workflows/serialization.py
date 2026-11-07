"""Deterministic serialization of job openings to CSV and JSON."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone

from pydantic import ValidationError

from .models import JobOpening, JobSearchOutput

CSV_COLUMNS = [
    "position",
    "company",
    "location",
    "description",
    "validation_criteria",
    "match_score",
    "source_url",
    "contact_email",
    "linkedin_url",
    "source",
    "found_at",
]


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
    """Deduplicate, rank, and serialize openings into the workflow output."""
    ranked = sorted(openings, key=lambda o: o.match_score, reverse=True)
    seen: set[tuple[str, str]] = set()
    unique: list[JobOpening] = []
    for opening in ranked:
        key = (opening.position.strip().lower(), opening.company.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(opening)

    unique.sort(key=lambda o: o.match_score, reverse=True)
    unique = unique[:max_openings]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for opening in unique:
        if not opening.found_at:
            opening.found_at = today

    return JobSearchOutput(
        cv_variant=cv_variant,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        openings=unique,
        csv=to_csv(unique),
    )


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
