"""Regression tests for the workflow wiring: imports, activity registration, discovery.

These cover the two defects that made the workflow unusable: a bad SDK import
and reading ``.final_output`` off a list of content chunks.
"""

from __future__ import annotations

import inspect

import mistralai.workflows as workflows
from mistralai.workflows.core.activity import get_wrapped_activity

ACTIVITY_NAMES = (
    "load_candidate_activity",
    "search_openings_activity",
    "validate_openings_activity",
    "build_output_activity",
)


def test_job_search_module_imports() -> None:
    import worker.workflows.job_search  # noqa: F401


def test_activities_are_registered() -> None:
    import worker.workflows.activities  # noqa: F401

    for name in ACTIVITY_NAMES:
        assert get_wrapped_activity(name) is not None, f"{name} is not registered"


def test_workflow_is_discoverable() -> None:
    import worker.workflows.job_search  # noqa: F401

    classes = workflows.discover_all_workflows_in_package("worker.workflows")
    names = [cls.__name__ for cls in classes]
    assert "JobSearchWorkflow" in names

    definition = workflows.get_workflow_definition(
        next(cls for cls in classes if cls.__name__ == "JobSearchWorkflow")
    )
    assert definition.name == "job-search"


def test_runner_output_is_joined_from_text_chunks() -> None:
    """Runner.run returns content chunks; the helper must not read .final_output."""
    from mistralai.client.models import TextChunk
    from worker.workflows.activities import _join_text

    chunks = [TextChunk(type="text", text="[{\"position\": "), TextChunk(type="text", text="\"x\"}]")]
    assert _join_text(chunks) == '[{"position": "x"}]'
    assert _join_text([]) == ""


def test_agent_runner_is_called_with_an_explicit_session() -> None:
    """Built-in tools need a RemoteSession; it must not be incidental."""
    from mistralai.workflows.plugins.mistralai import Runner

    source = inspect.getsource(Runner.run)
    assert "session: Session | None = None" in source
    from worker.workflows import activities

    assert "RemoteSession()" in inspect.getsource(activities)


def test_entrypoint_has_no_inline_non_determinism() -> None:
    """datetime/json work must live in activities, not the replayed workflow body."""
    from worker.workflows import job_search

    source = inspect.getsource(job_search)
    assert "datetime.now" not in source
    assert "load_candidate(" not in source
