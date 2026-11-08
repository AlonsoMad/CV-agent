"""Data models for the job-search workflow."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CandidateProfile(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    github: str = ""
    location: str = ""
    open_to_relocation: bool = True
    summary: str = ""
    target_roles: list[str] = Field(default_factory=list)
    years_of_experience: float | None = None
    key_skills: list[str] = Field(default_factory=list)
    languages: dict[str, str] = Field(default_factory=dict)
    preferences: dict[str, object] = Field(default_factory=dict)
    cv_text: str = ""


class JobOpening(BaseModel):
    position: str
    company: str
    location: str = ""
    description: str = ""
    validation_criteria: str = ""
    match_score: int = 0
    source_url: str = ""
    contact_email: str = ""
    linkedin_url: str = ""
    source: str = "web"
    found_at: str = ""


class JobSearchInput(BaseModel):
    cv_variant: str = "forward_deployed"
    max_openings: int = Field(default=10, ge=1, le=50)
    profile_override: CandidateProfile | None = None


class JobSearchOutput(BaseModel):
    cv_variant: str
    generated_at: str
    openings: list[JobOpening]
    csv: str
