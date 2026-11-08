"""Loading of candidate profile and CV data packaged with the worker."""

from __future__ import annotations

import importlib.resources
import json
from typing import Any

import yaml

from .models import CandidateProfile

CV_VARIANTS = {
    "forward_deployed": "cv_forward_deployed.md",
    "industry": "cv_industry.md",
}


def _read_data_file(name: str) -> str:
    resource = importlib.resources.files("worker.candidate_data").joinpath(name)
    return resource.read_text(encoding="utf-8")


def load_profile() -> dict[str, Any]:
    profile = yaml.safe_load(_read_data_file("profile.yaml"))
    if not isinstance(profile, dict):
        raise ValueError("candidate_data/profile.yaml must contain a mapping")
    return profile


def load_cv_text(variant: str) -> str:
    filename = CV_VARIANTS.get(variant)
    if filename is None:
        raise ValueError(f"Unknown CV variant '{variant}'. Valid variants: {sorted(CV_VARIANTS)}")
    return _read_data_file(filename)


def load_candidate(variant: str) -> dict[str, Any]:
    """Return the full candidate context (profile + CV text) as a JSON-ready dict."""
    profile = load_profile()
    candidate = dict(profile)
    candidate["cv_text"] = load_cv_text(variant)
    return candidate


def candidate_to_json(candidate: dict[str, Any]) -> str:
    return json.dumps(candidate, ensure_ascii=False, indent=2)
