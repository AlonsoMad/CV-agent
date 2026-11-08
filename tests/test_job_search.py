"""Tests for the job-search workflow: serialization, candidate loading, and orchestration."""

from __future__ import annotations

import csv
import io
import json

import pytest

from worker.workflows.candidate import load_candidate
from worker.workflows.models import JobOpening
from worker.workflows.serialization import build_output, parse_openings

SAMPLE_OPENINGS = [
    JobOpening(
        position="AI Engineer",
        company="Acme AI",
        location="Madrid",
        description="Build agentic systems for enterprise clients.",
        validation_criteria="LangGraph experience; Python; client-facing work",
        match_score=85,
        source_url="https://example.com/jobs/1",
        source="web",
    ),
    JobOpening(
        position="Forward Deployed Engineer",
        company="Beta Corp",
        location="Paris",
        description="Deploy AI solutions for clients.",
        validation_criteria="Deployment experience; Python",
        match_score=70,
        source_url="https://example.com/jobs/2",
        source="linkedin",
    ),
]


def test_parse_openings_from_noisy_llm_text() -> None:
    raw = "Here are the openings:\n```json\n" + json.dumps(
        [opening.model_dump() for opening in SAMPLE_OPENINGS]
    ) + "\n```\nDone."
    openings = parse_openings(raw)
    assert len(openings) == 2
    assert openings[0].company == "Acme AI"
    assert openings[1].match_score == 70


def test_parse_openings_returns_empty_on_garbage() -> None:
    assert parse_openings("no json here at all") == []


def test_csv_output_is_parsable_and_ordered() -> None:
    output = build_output("forward_deployed", SAMPLE_OPENINGS, max_openings=10)
    rows = list(csv.DictReader(io.StringIO(output.csv)))
    assert len(rows) == 2
    assert rows[0]["position"] == "AI Engineer"
    assert rows[0]["match_score"] == "85"
    assert rows[1]["position"] == "Forward Deployed Engineer"


def test_csv_quoting_survives_commas_quotes_and_newlines() -> None:
    messy = JobOpening(
        position="Engineer, Backend",
        company='Quotes "R" Us',
        description="Line one\nLine two",
        validation_criteria="skills; more, skills",
        match_score=50,
        source_url="https://example.com/jobs/3",
    )
    output = build_output("forward_deployed", [messy], max_openings=10)
    rows = list(csv.DictReader(io.StringIO(output.csv)))
    assert rows[0]["position"] == "Engineer, Backend"
    assert rows[0]["description"] == "Line one\nLine two"
    assert rows[0]["company"] == 'Quotes "R" Us'


def test_build_output_dedupes_and_caps() -> None:
    extra = JobOpening(
        position="AI Engineer",
        company="Acme AI",
        match_score=99,
        source_url="https://example.com/jobs/1",
    )
    output = build_output("forward_deployed", [*SAMPLE_OPENINGS, extra], max_openings=2)
    assert len(output.openings) == 2
    assert output.openings[0].match_score == 99
    assert all(opening.found_at for opening in output.openings)


def test_load_candidate_rejects_unknown_variant() -> None:
    with pytest.raises(ValueError):
        load_candidate("does_not_exist")
