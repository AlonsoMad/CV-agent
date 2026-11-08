"""Tests for the job-search workflow: serialization, contacts, candidate loading."""

from __future__ import annotations

import asyncio
import csv
import io
import json

import pytest

from worker.workflows.candidate import load_candidate
from worker.workflows.contacts import (
    contact_kind,
    extract_email,
    extract_linkedin,
    normalize_linkedin,
)
from worker.workflows.models import JobOpening
from worker.workflows.serialization import CSV_COLUMNS, build_output, parse_openings

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


# --- contact extraction ---------------------------------------------------


def test_extract_email_skips_images_and_noreply() -> None:
    assert extract_email("reach logo@2x.png for details") == ""
    assert extract_email("write to noreply@acme.com") == ""
    assert extract_email("apply via jobs@acme.com.") == "jobs@acme.com"


def test_extract_email_ignores_example_domains() -> None:
    assert extract_email("contact hr@example.com") == ""


def test_extract_linkedin_prefers_job_posting() -> None:
    text = (
        "Recruiter: https://www.linkedin.com/in/jane-doe "
        "Posting: https://www.linkedin.com/jobs/view/123?trk=x"
    )
    assert extract_linkedin(text) == "https://www.linkedin.com/jobs/view/123"


def test_normalize_linkedin_forces_https_and_strips_query() -> None:
    assert (
        normalize_linkedin("http://es.linkedin.com/in/jane-doe/?trk=abc#top")
        == "https://www.linkedin.com/in/jane-doe"
    )
    assert normalize_linkedin("https://notlinkedin.com/in/jane") == ""


def test_contact_kind_precedence() -> None:
    assert contact_kind("a@b.com", "https://www.linkedin.com/in/x", "https://x.test") == "email"
    assert contact_kind("", "https://www.linkedin.com/in/x", "https://x.test") == "linkedin"
    assert contact_kind("", "", "https://x.test") == "url"
    assert contact_kind("", "", "") == "none"


def test_build_output_fills_contacts_from_description() -> None:
    opening = JobOpening(
        position="ML Engineer",
        company="Gamma",
        match_score=60,
        description="Mail hiring@gamma.io or see https://www.linkedin.com/in/recruiter-gamma",
    )
    output = build_output("forward_deployed", [opening], max_openings=5)
    row = output.openings[0]
    assert row.contact_email == "hiring@gamma.io"
    assert row.linkedin_url == "https://www.linkedin.com/in/recruiter-gamma"
    assert row.contact_kind == "email"


def test_model_contacts_win_over_extraction() -> None:
    opening = JobOpening(
        position="ML Engineer",
        company="Gamma",
        match_score=60,
        description="Mail hiring@gamma.io",
        contact_email="talent@gamma.io",
    )
    output = build_output("forward_deployed", [opening], max_openings=5)
    assert output.openings[0].contact_email == "talent@gamma.io"


# --- schema ---------------------------------------------------------------


def test_opening_id_stable_and_dedupe_by_url() -> None:
    first = JobOpening(
        position="AI Engineer",
        company="Acme AI",
        match_score=80,
        source_url="https://acme.test/jobs/1",
    )
    same_opening_other_casing = JobOpening(
        position="ai engineer",
        company="ACME ai",
        match_score=70,
        source_url="https://acme.test/jobs/1/",
    )
    output = build_output("forward_deployed", [first, same_opening_other_casing], max_openings=10)
    assert len(output.openings) == 1
    assert output.openings[0].match_score == 80

    again = build_output("forward_deployed", [first], max_openings=10)
    assert again.openings[0].opening_id == output.openings[0].opening_id
    assert output.openings[0].opening_id


def test_dedupe_by_url_across_different_titles() -> None:
    a = JobOpening(
        position="AI Engineer", company="Acme", match_score=90,
        source_url="https://acme.test/jobs/1",
    )
    b = JobOpening(
        position="Machine Learning Engineer", company="Acme", match_score=50,
        source_url="https://acme.test/jobs/1",
    )
    output = build_output("forward_deployed", [a, b], max_openings=10)
    assert len(output.openings) == 1
    assert output.openings[0].position == "AI Engineer"


def test_csv_columns_exact_order() -> None:
    output = build_output("forward_deployed", SAMPLE_OPENINGS, max_openings=10)
    assert next(csv.reader(io.StringIO(output.csv))) == CSV_COLUMNS


def test_output_reports_count_and_schema_version() -> None:
    output = build_output("forward_deployed", SAMPLE_OPENINGS, max_openings=10)
    assert output.count == len(output.openings) == 2
    assert output.schema_version == "1"


def test_build_output_activity_returns_json_serializable() -> None:
    from mistralai.workflows.core.activity import get_wrapped_activity

    inner = get_wrapped_activity("build_output_activity")
    assert inner is not None
    payload = json.dumps([opening.model_dump() for opening in SAMPLE_OPENINGS])
    result = asyncio.run(inner("forward_deployed", payload, 10))

    assert isinstance(result, dict)
    assert json.loads(json.dumps(result)) == result
    assert result["count"] == 2
    rows = list(csv.DictReader(io.StringIO(result["csv"])))
    assert len(rows) == 2
    assert rows[0]["position"] == "AI Engineer"


def test_build_output_activity_tolerates_unparsable_input() -> None:
    from mistralai.workflows.core.activity import get_wrapped_activity

    inner = get_wrapped_activity("build_output_activity")
    result = asyncio.run(inner("forward_deployed", "the validator returned prose", 10))
    assert result["count"] == 0
    assert result["openings"] == []
