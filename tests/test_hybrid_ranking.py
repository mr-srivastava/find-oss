from collections.abc import Callable
from datetime import datetime

from find_oss.hybrid_ranking import (
    is_semantic_enrichment_eligible,
    score_issue,
    score_repository,
)
from find_oss.models import GitHubIssue, GitHubRepository, SearchIntent


def test_repository_scores_are_deterministic_and_penalize_archived(
    repository_factory: Callable[..., GitHubRepository],
    fixed_now: datetime,
) -> None:
    intent = SearchIntent(
        query="Python AI agents with MIT license",
        languages=["Python"],
        topics=["AI", "agents"],
        licenses=["MIT"],
    )

    active = score_repository(repository_factory(), intent, now=fixed_now)
    archived = score_repository(
        repository_factory(archived=True), intent, now=fixed_now
    )

    assert active.relevance == 10
    assert active.license == 10
    assert active.health > archived.health


def test_missing_license_scores_zero(
    repository_factory: Callable[..., GitHubRepository],
    fixed_now: datetime,
) -> None:
    scores = score_repository(
        repository_factory(license_spdx=None),
        SearchIntent(query="agents"),
        now=fixed_now,
    )
    assert scores.license == 0


def test_beginner_issue_scores_accessibility_highly(
    repository_factory: Callable[..., GitHubRepository],
    issue_factory: Callable[..., GitHubIssue],
    fixed_now: datetime,
) -> None:
    issue = issue_factory(
        title="Improve beginner documentation",
        labels=["good first issue", "documentation"],
    )

    scores = score_issue(
        issue,
        repository_factory(),
        SearchIntent(query="beginner docs"),
        fixed_now,
    )

    assert scores.accessibility >= 9


def test_semantic_enrichment_skips_well_documented_generic_search(
    repository_factory: Callable[..., GitHubRepository],
) -> None:
    repo = repository_factory()
    assert not is_semantic_enrichment_eligible(
        repo, SearchIntent(query="Find active Python projects")
    )
    assert is_semantic_enrichment_eligible(
        repo, SearchIntent(query="Explain the architecture of Python agent projects")
    )
    assert is_semantic_enrichment_eligible(
        repository_factory(contributor_files=[]),
        SearchIntent(query="Find Python agent projects"),
    )
