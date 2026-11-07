import asyncio

import mistralai.workflows as workflows

from worker.workflows import job_search  # noqa: F401  (registers the workflow)


async def main() -> None:
    workflow_classes = workflows.discover_all_workflows_in_package("worker.workflows")
    await workflows.run_worker(workflow_classes)


if __name__ == "__main__":
    asyncio.run(main())
