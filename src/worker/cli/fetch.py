"""Fetch a finished job-search run and write its CSV and JSON to disk."""

from __future__ import annotations

import argparse
import json
import os
import sys

from .common import WORKFLOW_IDENTIFIER, build_client, fail


def _latest_execution_id(client) -> str:
    """Return the most recent completed execution id for the workflow."""
    response = client.workflows.runs.list_runs(
        workflow_identifier=WORKFLOW_IDENTIFIER,
        status=["COMPLETED"],
        order="desc",
    )
    executions = getattr(getattr(response, "result", None), "executions", None) or []
    if not executions:
        fail(f"no completed runs found for workflow '{WORKFLOW_IDENTIFIER}'")
    return executions[0].execution_id


def _write_outputs(result: dict, out_dir: str) -> tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    generated_at = str(result.get("generated_at") or "")
    date = generated_at[:10] or "unknown-date"

    csv_path = os.path.join(out_dir, f"job-search-{date}.csv")
    json_path = os.path.join(out_dir, f"job-search-{date}.json")

    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(result["csv"])
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
    return csv_path, json_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cv-agent-fetch",
        description="Write the CSV and JSON of a job-search execution to disk.",
    )
    parser.add_argument("--execution-id", help="Execution to fetch")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Fetch the most recent completed execution (default when no id is given)",
    )
    parser.add_argument("--out-dir", default="./out", help="Output directory (default: ./out)")
    args = parser.parse_args(argv)

    client = build_client()

    execution_id = args.execution_id
    if not execution_id:
        execution_id = _latest_execution_id(client)

    execution = client.workflows.executions.get_workflow_execution(execution_id=execution_id)
    result = execution.result
    if not result:
        print(
            f"error: execution {execution_id} has no result (status {execution.status})",
            file=sys.stderr,
        )
        return 1

    csv_path, json_path = _write_outputs(result, args.out_dir)
    print(f"execution: {execution_id} ({execution.status})")
    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
