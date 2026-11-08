"""Shared helpers for the cv-agent command-line tools."""

from __future__ import annotations

import os
import sys

from mistralai.client import Mistral

WORKFLOW_IDENTIFIER = "job-search"


def build_client() -> Mistral:
    """Create an API client, exiting with a clear message when the key is missing."""
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("error: MISTRAL_API_KEY is not set", file=sys.stderr)
        raise SystemExit(1)
    return Mistral(api_key=api_key)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)
