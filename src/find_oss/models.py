from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class SearchIntent(BaseModel):
    query: str
    languages: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    licenses: list[str] = Field(default_factory=list)
    experience_level: str | None = None
    available_time: str | None = None
    include_inactive: bool = False


class Evidence(BaseModel):
    claim: str
    url: str
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class GitHubRepository(BaseModel):
    full_name: str
    url: str
    description: str = ""
    language: str | None = None
    topics: list[str] = Field(default_factory=list)
    stars: int = 0
    forks: int = 0
    archived: bool = False
    license_spdx: str | None = None
    created_at: datetime
    updated_at: datetime
    pushed_at: datetime | None = None
    default_branch: str = "main"
    has_release: bool = False
    contributor_files: list[str] = Field(default_factory=list)


class GitHubIssue(BaseModel):
    repository: str
    number: int
    title: str
    url: str
    body_excerpt: str = ""
    labels: list[str] = Field(default_factory=list)
    comments: int = 0
    created_at: datetime
    updated_at: datetime


class SemanticFinding(BaseModel):
    repository: str
    query: str
    summary: str
    source: str = "GithubSearchTool"


class RateLimitState(BaseModel):
    remaining: int | None = None
    reset_at: datetime | None = None


class RunMetrics(BaseModel):
    github_requests: int = 0
    cache_hits: int = 0
    semantic_searches: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    elapsed_seconds: float = 0
    partial_failures: list[str] = Field(default_factory=list)
    rate_limit: RateLimitState | None = None


class ScoreBreakdown(BaseModel):
    relevance: float = Field(ge=0, le=10)
    health: float = Field(ge=0, le=10)
    maturity: float = Field(ge=0, le=10)
    license: float = Field(ge=0, le=10)
    accessibility: float = Field(ge=0, le=10)

    @property
    def total(self) -> float:
        return round(
            (
                self.relevance * 0.35
                + self.health * 0.2
                + self.maturity * 0.15
                + self.license * 0.1
                + self.accessibility * 0.2
            ),
            2,
        )


class ToolCandidate(BaseModel):
    name: str
    url: str
    description: str = ""
    match_reason: str
    license: str | None = None
    archived: bool = False
    low_activity: bool = False
    evidence: list[Evidence] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    scores: ScoreBreakdown
    next_action: str = ""


class ContributionCandidate(BaseModel):
    repository: str
    issue_number: int
    title: str
    url: str
    match_reason: str
    difficulty: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    scores: ScoreBreakdown
    next_action: str = ""


class DiscoveryResults(BaseModel):
    intent: SearchIntent
    tools: list[ToolCandidate] = Field(default_factory=list)
    opportunities: list[ContributionCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvaluationResults(BaseModel):
    intent: SearchIntent
    tools: list[ToolCandidate] = Field(default_factory=list)
    opportunities: list[ContributionCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DiscoveryReport(BaseModel):
    query: str
    summary: str
    tools: list[ToolCandidate] = Field(default_factory=list)
    opportunities: list[ContributionCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: RunMetrics | None = None
