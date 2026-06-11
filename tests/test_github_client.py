from datetime import datetime, timezone

import pytest

from find_oss.github_client import (
    GitHubAuthenticationError,
    GitHubClient,
    GitHubRateLimitError,
)
from find_oss.models import GitHubRepository


class FakeResponse:
    def __init__(
        self,
        payload: object,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.payload = payload
        self.status = status
        self.headers = headers or {}

    def read(self) -> bytes:
        import json

        return json.dumps(self.payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_repository_search_is_bounded_and_compact() -> None:
    requests = []

    def opener(request, timeout):
        requests.append(request)
        return FakeResponse(
            {
                "items": [
                    {
                        "full_name": "acme/project",
                        "html_url": "https://github.com/acme/project",
                        "description": "Agent framework",
                        "language": "Python",
                        "topics": ["agents"],
                        "stargazers_count": 42,
                        "forks_count": 4,
                        "archived": False,
                        "license": {"spdx_id": "MIT"},
                        "created_at": "2024-01-01T00:00:00Z",
                        "updated_at": "2026-06-01T00:00:00Z",
                        "pushed_at": "2026-06-01T00:00:00Z",
                        "default_branch": "main",
                        "ignored_large_field": "x" * 1000,
                    }
                ]
            }
        )

    client = GitHubClient("token", opener=opener)
    results = client.search_repositories("python agents", limit=99)

    assert len(results) == 1
    assert results[0].full_name == "acme/project"
    assert results[0].license_spdx == "MIT"
    assert not hasattr(results[0], "ignored_large_field")
    assert "per_page=20" in requests[0].full_url
    assert requests[0].method == "GET"


def test_issue_search_forces_open_issues_and_limit() -> None:
    requests = []

    def opener(request, timeout):
        requests.append(request)
        return FakeResponse({"items": []})

    GitHubClient("token", opener=opener).search_issues("label:beginner", limit=90)

    assert "is%3Aissue" in requests[0].full_url
    assert "is%3Aopen" in requests[0].full_url
    assert "per_page=30" in requests[0].full_url


def test_client_caches_identical_requests_during_run() -> None:
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        return FakeResponse({"items": []})

    client = GitHubClient("token", opener=opener)
    client.search_repositories("agents")
    client.search_repositories("agents")

    assert calls == 1
    assert client.metrics.request_count == 1
    assert client.metrics.cache_hits == 1


@pytest.mark.parametrize(
    ("status", "error_type"),
    [(401, GitHubAuthenticationError), (403, GitHubRateLimitError)],
)
def test_client_translates_authentication_and_rate_limits(
    status: int, error_type: type[Exception]
) -> None:
    from urllib.error import HTTPError

    def opener(request, timeout):
        raise HTTPError(
            request.full_url,
            status,
            "failed",
            {"X-RateLimit-Remaining": "0"},
            None,
        )

    with pytest.raises(error_type):
        GitHubClient("token", opener=opener).search_repositories("agents")


def test_rate_limit_state_is_recorded() -> None:
    reset = int(datetime(2026, 6, 12, tzinfo=timezone.utc).timestamp())

    def opener(request, timeout):
        return FakeResponse(
            {"resources": {"search": {"remaining": 23, "reset": reset}}},
            headers={"X-RateLimit-Remaining": "23", "X-RateLimit-Reset": str(reset)},
        )

    state = GitHubClient("token", opener=opener).get_rate_limit()

    assert state.remaining == 23
    assert state.reset_at.year == 2026


def test_repository_enrichment_checks_release_and_contributor_files() -> None:
    def opener(request, timeout):
        if request.full_url.endswith("/releases?per_page=1"):
            return FakeResponse([{"tag_name": "v1.0"}])
        if "/contents/" in request.full_url:
            if request.full_url.endswith("/contents/CONTRIBUTING.md"):
                return FakeResponse({"name": "CONTRIBUTING.md"})
            from urllib.error import HTTPError

            raise HTTPError(request.full_url, 404, "missing", {}, None)
        raise AssertionError(request.full_url)

    client = GitHubClient("token", opener=opener)
    enriched = client.enrich_repository(
        GitHubRepository(
            full_name="acme/project",
            url="https://github.com/acme/project",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2026-06-01T00:00:00Z",
        )
    )

    assert enriched.has_release
    assert enriched.contributor_files == ["CONTRIBUTING.md"]
