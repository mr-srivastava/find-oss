from __future__ import annotations

import math
from datetime import datetime, timezone

from find_oss.models import (
    GitHubIssue,
    GitHubRepository,
    ScoreBreakdown,
    SearchIntent,
)

BEGINNER_LABELS = {
    "good first issue",
    "beginner",
    "help wanted",
    "documentation",
    "first-timers-only",
}


def _matches(values: list[str], expected: list[str]) -> float:
    if not expected:
        return 1.0
    normalized = {value.lower() for value in values}
    wanted = {value.lower() for value in expected}
    return len(normalized & wanted) / len(wanted)


def score_repository(
    repository: GitHubRepository,
    intent: SearchIntent,
    *,
    now: datetime | None = None,
) -> ScoreBreakdown:
    current = now or datetime.now(timezone.utc)
    language_match = _matches(
        [repository.language] if repository.language else [], intent.languages
    )
    topic_match = _matches(
        repository.topics
        + repository.description.lower().split()
        + repository.full_name.lower().split("/"),
        intent.topics,
    )
    relevance = 10 * ((language_match + topic_match) / 2)

    last_activity = repository.pushed_at or repository.updated_at
    inactive_days = max((current - last_activity).days, 0)
    health = max(0.0, 10 - inactive_days / 90)
    if repository.archived:
        health = 0

    adoption = min(5.0, math.log10(repository.stars + repository.forks + 1) * 2)
    age_years = max((current - repository.created_at).days / 365, 0)
    maturity = min(10.0, adoption + min(age_years, 3) + (2 if repository.has_release else 0))

    if repository.license_spdx:
        license_score = (
            10.0
            if not intent.licenses
            or repository.license_spdx.lower()
            in {item.lower() for item in intent.licenses}
            else 2.0
        )
    else:
        license_score = 0.0

    accessibility = min(
        10.0,
        4
        + (4 if repository.contributor_files else 0)
        + (2 if inactive_days <= 90 else 0),
    )
    return ScoreBreakdown(
        relevance=round(relevance, 2),
        health=round(health, 2),
        maturity=round(maturity, 2),
        license=license_score,
        accessibility=accessibility,
    )


def score_issue(
    issue: GitHubIssue,
    repository: GitHubRepository,
    intent: SearchIntent,
    now: datetime,
) -> ScoreBreakdown:
    repo_scores = score_repository(repository, intent, now=now)
    labels = {label.lower() for label in issue.labels}
    beginner = bool(labels & BEGINNER_LABELS)
    detail = bool(issue.body_excerpt.strip())
    recent = (now - issue.updated_at).days <= 90
    accessibility = min(
        10.0,
        3 + (4 if beginner else 0) + (2 if detail else 0) + (1 if recent else 0),
    )
    return ScoreBreakdown(
        relevance=repo_scores.relevance,
        health=repo_scores.health,
        maturity=repo_scores.maturity,
        license=repo_scores.license,
        accessibility=accessibility,
    )


def is_semantic_enrichment_eligible(
    repository: GitHubRepository, intent: SearchIntent
) -> bool:
    semantic_terms = {
        "architecture",
        "implementation",
        "internals",
        "codebase",
        "how it works",
    }
    query = intent.query.lower()
    return not repository.contributor_files or any(term in query for term in semantic_terms)
