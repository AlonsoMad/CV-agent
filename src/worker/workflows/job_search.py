"""Job-search workflow: orchestration only.

All I/O, clocks and model calls live in ``activities``; this module must stay
deterministic so it can be replayed.
"""

from __future__ import annotations

from datetime import timedelta

import mistralai.workflows as workflows

from .activities import (
    SEARCH_INSTRUCTIONS,
    VALIDATION_INSTRUCTIONS,
    build_output_activity,
    load_candidate_activity,
    search_openings_activity,
    validate_openings_activity,
)
from .models import JobSearchInput, JobSearchOutput

__all__ = [
    "JobSearchWorkflow",
    "SEARCH_INSTRUCTIONS",
    "VALIDATION_INSTRUCTIONS",
]


@workflows.workflow.define(
    name="job-search",
    workflow_display_name="Job Search Agent",
    workflow_description=(
        "Finds job openings matching the candidate CV using web search, validates each fit, "
        "and returns a parsable CSV plus JSON."
    ),
    execution_timeout=timedelta(minutes=45),
)
class JobSearchWorkflow:
    @workflows.workflow.entrypoint
    async def run(self, job_input: JobSearchInput) -> JobSearchOutput:
        override = (
            job_input.profile_override.model_dump(exclude_none=True)
            if job_input.profile_override is not None
            else None
        )

        candidate_json = await load_candidate_activity(job_input.cv_variant, override)
        raw = await search_openings_activity(candidate_json, job_input.max_openings)
        validated = await validate_openings_activity(candidate_json, raw)

        # The validator may legitimately return nothing; fall back to the raw
        # search result rather than dropping the run. The activity logs the
        # fallback so it is observable.
        result = await build_output_activity(
            job_input.cv_variant,
            validated.strip() or raw,
            job_input.max_openings,
        )
        return JobSearchOutput.model_validate(result)
