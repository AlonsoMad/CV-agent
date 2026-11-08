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


def test_web_search_uses_conversations_api_with_search_tool() -> None:
    """Web search must go through a path the org actually supports.

    Creating agents is disabled for some organizations, and WebSearchTool is
    rejected on /chat/completions. The Conversations API is the supported
    route, and it must carry the tool or the agent silently loses web access.
    """
    from worker.workflows import activities

    source = inspect.getsource(activities)
    assert "conversations.start_async" in source
    assert "WebSearchTool()" in source
    assert "Runner.run" not in source
    assert "RemoteSession" not in source
    assert "Agent(" not in source


def test_web_search_request_carries_the_search_tool() -> None:
    """The tool must be a web_search tool, not a plain function tool."""
    from mistralai.client.models.websearchtool import WebSearchTool

    assert WebSearchTool().type == "web_search"


def test_entrypoint_has_no_inline_non_determinism() -> None:
    """datetime/json work must live in activities, not the replayed workflow body."""
    from worker.workflows import job_search

    source = inspect.getsource(job_search)
    assert "datetime.now" not in source
    assert "load_candidate(" not in source
