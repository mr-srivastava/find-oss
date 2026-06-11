from find_oss.models import (
    ContributionCandidate,
    Evidence,
    ScoreBreakdown,
    ToolCandidate,
)
from find_oss.ranking import deduplicate_contributions, deduplicate_tools, rank_tools


def _scores(total: float) -> ScoreBreakdown:
    return ScoreBreakdown(
        relevance=total,
        health=total,
        maturity=total,
        license=total,
        accessibility=total,
    )


def test_deduplicates_repositories_by_canonical_url_and_keeps_best() -> None:
    low = ToolCandidate(
        name="Example",
        url="https://github.com/Org/Repo/",
        match_reason="low",
        scores=_scores(3),
    )
    high = low.model_copy(
        update={"url": "https://github.com/org/repo", "scores": _scores(9)}
    )

    assert deduplicate_tools([low, high]) == [high]


def test_deduplicates_issues_by_repository_and_number() -> None:
    first = ContributionCandidate(
        repository="Org/Repo",
        issue_number=42,
        title="Issue",
        url="https://github.com/Org/Repo/issues/42",
        match_reason="match",
        scores=_scores(5),
    )
    duplicate = first.model_copy(update={"repository": "org/repo"})

    assert deduplicate_contributions([first, duplicate]) == [first]


def test_archived_repository_is_penalized_without_explicit_request() -> None:
    active = ToolCandidate(
        name="Active",
        url="https://github.com/acme/active",
        match_reason="match",
        scores=_scores(6),
        evidence=[Evidence(claim="Active", url="https://github.com/acme/active")],
    )
    archived = ToolCandidate(
        name="Archived",
        url="https://github.com/acme/archived",
        match_reason="match",
        scores=_scores(9),
        archived=True,
    )

    ranked = rank_tools([archived, active], include_inactive=False)
    assert ranked[0].name == "Active"

