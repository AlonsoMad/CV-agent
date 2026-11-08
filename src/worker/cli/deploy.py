"""Create (or restart) a Mistral managed deployment of the job-search worker."""

from __future__ import annotations

import argparse

from .common import build_client, fail


def create_deployment(
    client,
    name: str,
    repo_url: str,
    revision: str = "main",
    dockerfile_path: str = "Dockerfile",
    build_directory: str | None = None,
):
    backend_spec: dict[str, str] = {
        "type": "mistral_cloud",
        "dockerfile_path": dockerfile_path,
    }
    if build_directory:
        backend_spec["build_directory"] = build_directory
    return client.workflows.deployments.create_deployment(
        name=name,
        spec={
            "github_url": repo_url,
            "revision": revision,
            "backend_spec": backend_spec,
        },
    )


def _describe(deployment) -> None:
    print(f"name:   {deployment.name}")
    print(f"status: {getattr(deployment, 'status', 'unknown')}")
    worker = getattr(deployment, "worker", None)
    if worker is not None:
        print(f"worker: {worker}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cv-agent-deploy",
        description="Create a Mistral managed deployment for the job-search worker.",
    )
    parser.add_argument("--name", required=True, help="Deployment name, e.g. cv-agent")
    parser.add_argument(
        "--repo", required=True, help="GitHub repo URL, e.g. https://github.com/owner/repo"
    )
    parser.add_argument("--revision", default="main", help="Git revision to build (default: main)")
    parser.add_argument(
        "--dockerfile", default="Dockerfile", help="Path to the Dockerfile (default: Dockerfile)"
    )
    parser.add_argument(
        "--build-directory", default=None, help="Subdirectory to build from, if any"
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart an existing deployment instead of creating one",
    )
    args = parser.parse_args(argv)

    client = build_client()

    if args.restart:
        try:
            deployment = client.workflows.deployments.restart_deployment(name=args.name)
        except Exception as exc:  # noqa: BLE001 - surface the API error verbatim
            fail(f"could not restart deployment '{args.name}': {exc}")
        print("restarted deployment")
        _describe(deployment)
        return 0

    try:
        deployment = create_deployment(
            client,
            name=args.name,
            repo_url=args.repo,
            revision=args.revision,
            dockerfile_path=args.dockerfile,
            build_directory=args.build_directory,
        )
    except Exception as exc:  # noqa: BLE001 - surface the API error verbatim
        fail(
            f"could not create deployment '{args.name}': {exc}\n"
            "If it already exists, use --restart to redeploy."
        )

    print("created deployment")
    _describe(deployment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
