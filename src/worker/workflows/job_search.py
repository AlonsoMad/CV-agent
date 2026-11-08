"""Job-search agent: find, validate, and rank job openings for a candidate CV."""

from __future__ import annotations

import json
from datetime import timedelta

import mistralai.workflows as workflows
from mistralai.client.models import WebSearchTool
from mistralai.workflows.plugins.mistralai import Agent, Runner

from .candidate import candidate_to_json, load_candidate
from .models import JobSearchInput, JobSearchOutput
from .serialization import build_output, parse_openings

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
(skills matched, seniority, location, language), separated by semicolons.
- source_url: the URL of the job posting or page where you found it.
- contact_email: recruiter or careers email if you found one, otherwise empty.
- linkedin_url: the job posting's or recruiter's LinkedIn URL if you found one, otherwise empty.
- source: one of "web", "linkedin", "career_page".
- match_score: integer 0-100 estimating how well the opening fits the candidate.

Return ONLY a strict JSON array of opening objects, no prose, no markdown fences."""

VALIDATION_INSTRUCTIONS = """You are a job-fit validator. You are given a candidate profile (as JSON) \
and a JSON array of job openings. For each opening:
- verify with your web search tool that the posting is plausible and still reachable;
- write validation_criteria: 1-3 concrete, checkable bullets (joined with "; ") explaining why the \
candidate fits, referencing the candidate's actual skills and experience;
- set match_score: integer 0-100 for how well the opening fits the candidate;
- drop openings you could not verify or that clearly do not fit.

Return ONLY a strict JSON array of the openings that passed, each with all its original fields \
plus your updated validation_criteria and match_score."""


@workflows.activity(start_to_close_timeout=timedelta(seconds=1200))
async def search_openings(candidate_json: str, max_openings: int) -> str:
    agent = Agent(
        name="job-search-web-searcher",
        model=DEFAULT_MODEL,
        instructions=SEARCH_INSTRUCTIONS,
        tools=[WebSearchTool(type="web_search")],
    )
    result = await Runner.run(
        agent=agent,
        inputs=(
            f"{candidate_json}\n\nFind up to {max_openings} current, real job openings that fit "
            "this candidate. Return only the strict JSON array."
        ),
    )
    return result.final_output


@workflows.activity(start_to_close_timeout=timedelta(seconds=1200))
async def validate_openings(candidate_json: str, openings_json: str) -> str:
    agent = Agent(
        name="job-fit-validator",
        model=DEFAULT_MODEL,
        instructions=VALIDATION_INSTRUCTIONS,
        tools=[WebSearchTool(type="web_search")],
    )
    result = await Runner.run(
        agent=agent,
        inputs=(
            f"Candidate profile:\n{candidate_json}\n\nOpenings to validate:\n{openings_json}\n\n"
            "Return only the strict JSON array of validated openings."
        ),
    )
    return result.final_output


@workflows.workflow.define(
    name="job-search",
    workflow_display_name="Job Search Agent",
    workflow_description=(
        "Finds job openings matching the candidate CV using web search, validates each fit, "
        "and returns a parsable CSV plus JSON."
    ),
)
class JobSearchWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, job_input: JobSearchInput) -> JobSearchOutput:
        candidate = load_candidate(job_input.cv_variant)
        if job_input.profile_override is not None:
            override = job_input.profile_override.model_dump(exclude_none=True)
            candidate.update(override)

        candidate_json = candidate_to_json(candidate)

        search_response = await search_openings(candidate_json, job_input.max_openings)
        openings = parse_openings(search_response)

        validated_response = await validate_openings(candidate_json, json_dumps(openings))
        validated = parse_openings(validated_response)
        rows = validated if validated else openings

        return build_output(job_input.cv_variant, rows, job_input.max_openings)


def json_dumps(value: list) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
