from collections.abc import Callable
from datetime import datetime, timezone

import pytest

from find_oss.models import DiscoveryReport, GitHubIssue, GitHubRepository


FIXED_NOW = datetime(2026, 6, 12, tzinfo=timezone.utc)


@pytest.fixture
def fixed_now() -> datetime:
    return FIXED_NOW


@pytest.fixture
def repository_factory() -> Callable[..., GitHubRepository]:
    def create(index: int = 0, **updates: object) -> GitHubRepository:
        values = {
            "full_name": f"acme/project-{index}",
            "url": f"https://github.com/acme/project-{index}",
            "description": "Python AI agent framework",
            "language": "Python",
            "topics": ["ai", "agents"],
            "stars": 100 - index,
            "forks": 10,
            "archived": False,
            "license_spdx": "MIT",
            "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
            "pushed_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
            "default_branch": "main",
            "has_release": True,
            "contributor_files": ["CONTRIBUTING.md"],
        }
        values.update(updates)
        return GitHubRepository(**values)

    return create


@pytest.fixture
def issue_factory() -> Callable[..., GitHubIssue]:
    def create(**updates: object) -> GitHubIssue:
        values = {
            "repository": "acme/project-0",
            "number": 1,
            "title": "Starter issue",
            "url": "https://github.com/acme/project-0/issues/1",
            "body_excerpt": "Clear acceptance criteria and links.",
            "labels": ["good first issue"],
            "comments": 2,
            "created_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 6, 10, tzinfo=timezone.utc),
        }
        values.update(updates)
        return GitHubIssue(**values)

    return create


@pytest.fixture
def report_factory() -> Callable[..., DiscoveryReport]:
    def create(**updates: object) -> DiscoveryReport:
        values = {"query": "Find agents", "summary": "Matches found."}
        values.update(updates)
        return DiscoveryReport(**values)

    return create
