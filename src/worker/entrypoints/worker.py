import asyncio
import logging
import os

import mistralai.workflows as workflows


async def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    # Discovery imports every module under worker.workflows, which registers the
    # workflow classes and their activities.
    workflow_classes = workflows.discover_all_workflows_in_package("worker.workflows")
    await workflows.run_worker(workflow_classes)


if __name__ == "__main__":
    asyncio.run(main())
