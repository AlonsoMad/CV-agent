"""Activities for the job-search workflow.

Every non-deterministic or I/O-bound step lives here: the workflow sandbox
forbids clocks and network calls, and replays workflow code, so anything that
must not repeat or diverge belongs in an activity.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta

import mistralai.workflows as workflows
from mistralai.client.models import TextChunk
from mistralai.client.models.websearchtool import WebSearchTool
from mistralai.workflows.plugins.mistralai import Agent, RemoteSession, Runner

from .candidate import candidate_to_json, load_candidate
from .models import JobOpening
from .serialization import build_output, parse_openings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "mistral-medium-latest"

SEARCH_INSTRUCTIONS = """You are a job-search agent. You are given a candidate profile (as JSON) \
and you must find real, current job openings that fit the candidate.

Use your web search tool extensively: search company career pages, job boards, and public \
LinkedIn job postings or recruiter profiles for the candidate's target roles, key skills, and \
preferred locations. Only include openings you actually found evidence for on the web.

For every opening you report, fill in every field:
- position, company, location: as advertised.
- description: 2-3 sentences on what the role is and why it fits the candidate.
- validation_criteria: 1-3 concrete, checkable reasons this opening fits the candidate \
(skills matched, seniority, location, language), separated by semicolons, each naming a \
specific item from the candidate profile.
- match_score: integer 0-100 estimating how well the opening fits the candidate.
- source_url: the exact URL of the job posting or page where you found it.
- contact_email: the recruiter or careers email ONLY if it is literally present on the page, \
otherwise "".
- linkedin_url: the job posting's or recruiter's LinkedIn URL ONLY if it is literally present \
on the page, otherwise "".
- source: one of "web", "linkedin", "career_page".

Never invent a URL, email or LinkedIn profile; leave the field empty instead.

Return ONLY a bare JSON array of opening objects: no prose, no markdown fences."""

VALIDATION_INSTRUCTIONS = """You are a job-fit validator. You are given a candidate profile (as JSON) \
and a JSON array of job openings. For each opening:
- re-open its source_url with your web search tool; keep the opening only if you could \
verify the posting is real and still reachable;
- rewrite validation_criteria: 1-3 concrete, checkable items separated by semicolons, each \
naming an actual skill, role or experience from the candidate profile;
- recompute match_score: integer 0-100 for how well the opening fits the candidate;
- preserve position, company, location, source_url, contact_email, linkedin_url, source and \
description verbatim from the input;
- drop every opening you could not verify or that clearly does not fit.

An empty array is an acceptable answer. Never invent a URL, email or LinkedIn profile.

Return ONLY a bare JSON array of the openings that passed, with no prose and no markdown \
fences."""


def _join_text(outputs: list) -> str:
    """Collect assistant text from a Runner.run result.

    ``Runner.run`` returns a list of content chunks, not an object with
    ``final_output``; only ``TextChunk`` items carry the model's prose.
    """
    return "".join(
        output.text for output in outputs if isinstance(output, TextChunk) and output.text
    )


async def _run_agent(name: str, instructions: str, inputs: str, max_turns: int) -> str:
    agent = Agent(
        name=name,
        model=DEFAULT_MODEL,
        instructions=instructions,
        tools=[WebSearchTool()],
    )
    outputs = await Runner.run(
        agent=agent,
        inputs=inputs,
        session=RemoteSession(),
        max_turns=max_turns,
    )
    return _join_text(outputs)


@workflows.activity(start_to_close_timeout=timedelta(seconds=1200), retry_policy_max_attempts=2)
async def load_candidate_activity(cv_variant: str, profile_override: dict | None) -> str:
    """Load the packaged profile + CV text and return it as JSON."""
    candidate = load_candidate(cv_variant)
    if profile_override is not None:
        candidate.update(profile_override)
    return candidate_to_json(candidate)


@workflows.activity(start_to_close_timeout=timedelta(seconds=1800), retry_policy_max_attempts=2)
async def search_openings_activity(candidate_json: str, max_openings: int) -> str:
    """Run the web-search agent and return its raw response text."""
    return await _run_agent(
        name="job-search-web-searcher",
        instructions=SEARCH_INSTRUCTIONS,
        inputs=(
            f"{candidate_json}\n\nFind up to {max_openings} current, real job openings that fit "
            "this candidate. Return only the bare JSON array."
        ),
        max_turns=12,
    )


@workflows.activity(start_to_close_timeout=timedelta(seconds=1200), retry_policy_max_attempts=2)
async def validate_openings_activity(candidate_json: str, openings_json: str) -> str:
    """Re-verify each opening against the web and return its raw response text."""
    return await _run_agent(
        name="job-fit-validator",
        instructions=VALIDATION_INSTRUCTIONS,
        inputs=(
            f"Candidate profile:\n{candidate_json}\n\nOpenings to validate:\n{openings_json}\n\n"
            "Return only the bare JSON array of validated openings."
        ),
        max_turns=8,
    )


@workflows.activity(start_to_close_timeout=timedelta(seconds=120))
async def build_output_activity(
    cv_variant: str, raw_openings_json: str, max_openings: int
) -> dict:
    """Parse, enrich, dedupe, rank and serialize openings into the final output."""
    openings = parse_openings(raw_openings_json)
    if not openings:
        logger.warning(
            "build_output_activity received no parsable openings (payload length %d)",
            len(raw_openings_json or ""),
        )
    return build_output(cv_variant, openings, max_openings).model_dump()


def dump_openings(openings: list[JobOpening]) -> str:
    """Serialize parsed openings for the validation activity's input."""
    return json.dumps(
        [opening.model_dump() for opening in openings], ensure_ascii=False, indent=2
    )
