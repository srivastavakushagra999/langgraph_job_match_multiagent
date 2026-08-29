from typing import Optional

from pydantic import BaseModel, Field


class JobListing(BaseModel):
    id: str
    slug: str
    position: str
    company: str
    tags: list[str]
    description: str
    location: str
    url: str
    date: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None


class Preferences(BaseModel):
    role: str
    remote: bool
    salary_min: float
    currency: str
    base_location: str
    open_to_onsite_at_base: bool
    additional_context: Optional[str] = None


class ScoredJob(BaseModel):
    job: JobListing
    fit_score: int = Field(ge=0, le=100)
    reasoning: str
    gap_suggestion: str

class OrchestratorDecision(BaseModel):
    expanded_keywords: list[str]
    context_signals: str


class JobScore(BaseModel):
    job_id: str
    fit_score: int = Field(ge=0, le=100)
    reasoning: str
    gap_suggestion: str


class ScoreAgentOutput(BaseModel):
    scores: list[JobScore]
