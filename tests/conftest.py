"""Test bootstrap.

Importing the workflow package registers its activities in the SDK's
process-global activity registry, which ``get_wrapped_activity`` reads. Doing it
once here keeps every test independent of import order.
"""

from __future__ import annotations

import worker.workflows.job_search  # noqa: F401  (imports and registers activities)
