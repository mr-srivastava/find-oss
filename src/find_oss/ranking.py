from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit, urlunsplit

from find_oss.models import ContributionCandidate, ToolCandidate


def canonical_github_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/").lower()
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def _tool_score(candidate: ToolCandidate, include_inactive: bool) -> float:
    score = candidate.scores.total
    if not include_inactive:
        if candidate.archived:
            score -= 6
        elif candidate.low_activity:
            score -= 2
    if not candidate.evidence:
        score -= 1
    return score


def rank_tools(
    candidates: Iterable[ToolCandidate], *, include_inactive: bool
) -> list[ToolCandidate]:
    return sorted(
        candidates,
        key=lambda item: _tool_score(item, include_inactive),
        reverse=True,
    )


def deduplicate_tools(candidates: Iterable[ToolCandidate]) -> list[ToolCandidate]:
    best: dict[str, ToolCandidate] = {}
    for candidate in candidates:
        key = canonical_github_url(candidate.url)
        current = best.get(key)
        if current is None or candidate.scores.total > current.scores.total:
            best[key] = candidate
    return list(best.values())


def deduplicate_contributions(
    candidates: Iterable[ContributionCandidate],
) -> list[ContributionCandidate]:
    unique: dict[tuple[str, int], ContributionCandidate] = {}
    for candidate in candidates:
        key = (candidate.repository.lower(), candidate.issue_number)
        unique.setdefault(key, candidate)
    return list(unique.values())

