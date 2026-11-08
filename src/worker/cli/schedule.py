"""Schedule the job-search workflow on a cron, and inspect or remove schedules."""

from __future__ import annotations

import argparse

from .common import WORKFLOW_IDENTIFIER, build_client, fail

# Overlap policy 1 = SKIP: a run that is still going must not be stacked.
OVERLAP_SKIP = 1
# Do not replay more than a day of missed runs after an outage.
CATCHUP_WINDOW_SECONDS = 86400


def schedule_workflow(
    client,
    deployment: str,
    cron: str,
    cv_variant: str,
    max_openings: int,
    timezone: str,
) -> str:
    response = client.workflows.schedules.schedule_workflow(
        workflow_identifier=WORKFLOW_IDENTIFIER,
        deployment_name=deployment,
        schedule={
            "input": {"cv_variant": cv_variant, "max_openings": max_openings},
            "cron_expressions": [cron],
            "time_zone_name": timezone,
            "policy": {
                "overlap": OVERLAP_SKIP,
                "catchup_window_seconds": CATCHUP_WINDOW_SECONDS,
            },
        },
    )
    return response.schedule_id


def list_schedules(client) -> None:
    response = client.workflows.schedules.get_schedules(workflow_name=WORKFLOW_IDENTIFIER)
    schedules = response.result.schedules if response is not None else []
    if not schedules:
        print(f"no schedules for workflow '{WORKFLOW_IDENTIFIER}'")
        return
    for schedule in schedules:
        cron = ",".join(schedule.cron_expressions or [])
        print(
            f"{schedule.schedule_id}  {schedule.workflow_name}  "
            f"paused={schedule.paused}  cron={cron}  deployment={schedule.deployment_name}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cv-agent-schedule",
        description="Schedule the job-search workflow on a Mistral managed deployment.",
    )
    parser.add_argument("--deployment", help="Target deployment name, e.g. cv-agent")
    parser.add_argument(
        "--cron", default="0 7 * * 1,4", help="Cron expression (default: Mon+Thu 07:00)"
    )
    parser.add_argument(
        "--cv-variant", default="forward_deployed", help="CV variant to search with"
    )
    parser.add_argument(
        "--max-openings", type=int, default=15, help="Maximum openings per run (default: 15)"
    )
    parser.add_argument("--timezone", default="UTC", help="Schedule time zone (default: UTC)")
    parser.add_argument("--list", action="store_true", help="List schedules and exit")
    parser.add_argument("--delete", metavar="SCHEDULE_ID", help="Delete a schedule and exit")
    args = parser.parse_args(argv)

    client = build_client()

    if args.list:
        list_schedules(client)
        return 0

    if args.delete:
        try:
            client.workflows.schedules.unschedule_workflow(schedule_id=args.delete)
        except Exception as exc:  # noqa: BLE001 - surface the API error verbatim
            fail(f"could not delete schedule '{args.delete}': {exc}")
        print(f"deleted schedule {args.delete}")
        return 0

    if not args.deployment:
        parser.error("--deployment is required unless --list or --delete is used")

    try:
        schedule_id = schedule_workflow(
            client,
            deployment=args.deployment,
            cron=args.cron,
            cv_variant=args.cv_variant,
            max_openings=args.max_openings,
            timezone=args.timezone,
        )
    except Exception as exc:  # noqa: BLE001 - surface the API error verbatim
        fail(f"could not schedule workflow: {exc}")

    print(f"schedule_id: {schedule_id}")
    print(f"cron: {args.cron} ({args.timezone})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
