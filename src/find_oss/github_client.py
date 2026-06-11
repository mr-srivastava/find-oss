from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from find_oss.models import GitHubIssue, GitHubRepository, RateLimitState

MAX_REPOSITORIES = 20
MAX_ISSUES = 30


class GitHubError(RuntimeError):
    pass


class GitHubAuthenticationError(GitHubError):
    pass


class GitHubPermissionError(GitHubError):
    pass


class GitHubRateLimitError(GitHubError):
    pass


class GitHubValidationError(GitHubError):
    pass


class GitHubNetworkError(GitHubError):
    pass


@dataclass
class GitHubMetrics:
    request_count: int = 0
    cache_hits: int = 0


class GitHubClient:
    def __init__(
        self,
        token: str,
        *,
        opener: Callable[..., object] = urlopen,
        timeout: int = 20,
    ) -> None:
        self.token = token
        self.opener = opener
        self.timeout = timeout
        self.metrics = GitHubMetrics()
        self._cache: dict[str, object] = {}
        self.rate_limit = RateLimitState()

    def _get(self, path: str, params: dict[str, object] | None = None) -> object:
        query = f"?{urlencode(params or {})}" if params else ""
        url = f"https://api.github.com{path}{query}"
        if url in self._cache:
            self.metrics.cache_hits += 1
            return self._cache[url]
        request = Request(
            url,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "find-oss",
            },
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
                headers = response.headers
        except HTTPError as error:
            remaining = error.headers.get("X-RateLimit-Remaining")
            if error.code == 401:
                raise GitHubAuthenticationError("GitHub authentication failed.") from error
            if error.code == 403 and remaining == "0":
                raise GitHubRateLimitError("GitHub API rate limit reached.") from error
            if error.code == 403:
                raise GitHubPermissionError("GitHub token lacks read permission.") from error
            if error.code == 422:
                raise GitHubValidationError("GitHub rejected the search query.") from error
            raise GitHubError(f"GitHub API returned HTTP {error.code}.") from error
        except (URLError, TimeoutError, socket.timeout) as error:
            raise GitHubNetworkError("Could not reach the GitHub API.") from error
        self.metrics.request_count += 1
        self._record_rate_limit(headers)
        self._cache[url] = payload
        return payload

    def _record_rate_limit(self, headers: object) -> None:
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        self.rate_limit = RateLimitState(
            remaining=int(remaining) if remaining is not None else None,
            reset_at=(
                datetime.fromtimestamp(int(reset), tz=timezone.utc)
                if reset is not None
                else None
            ),
        )

    def search_repositories(
        self, query: str, *, limit: int = MAX_REPOSITORIES
    ) -> list[GitHubRepository]:
        bounded = min(max(limit, 1), MAX_REPOSITORIES)
        payload = self._get(
            "/search/repositories",
            {"q": query, "per_page": bounded, "page": 1, "sort": "updated"},
        )
        return [self._repository(item) for item in payload.get("items", [])[:bounded]]

    def search_issues(
        self, query: str, *, limit: int = MAX_ISSUES
    ) -> list[GitHubIssue]:
        bounded = min(max(limit, 1), MAX_ISSUES)
        qualified = f"{query} is:issue is:open"
        payload = self._get(
            "/search/issues",
            {"q": qualified, "per_page": bounded, "page": 1, "sort": "updated"},
        )
        return [self._issue(item) for item in payload.get("items", [])[:bounded]]

    def get_repository(self, full_name: str) -> GitHubRepository:
        payload = self._get(f"/repos/{quote(full_name, safe='/')}")
        return self._repository(payload)

    def get_issue(self, repository: str, number: int) -> GitHubIssue:
        payload = self._get(
            f"/repos/{quote(repository, safe='/')}/issues/{number}"
        )
        return self._issue(payload, repository=repository)

    def get_rate_limit(self) -> RateLimitState:
        payload = self._get("/rate_limit")
        search = payload.get("resources", {}).get("search", {})
        reset = search.get("reset")
        return RateLimitState(
            remaining=search.get("remaining"),
            reset_at=(
                datetime.fromtimestamp(reset, tz=timezone.utc) if reset else None
            ),
        )

    def enrich_repository(
        self, repository: GitHubRepository
    ) -> GitHubRepository:
        base = f"/repos/{quote(repository.full_name, safe='/')}"
        has_release = False
        contributor_files: list[str] = []
        try:
            releases = self._get(f"{base}/releases", {"per_page": 1})
            has_release = bool(releases)
        except GitHubError:
            pass
        for filename in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md"):
            try:
                self._get(f"{base}/contents/{quote(filename, safe='/')}")
            except GitHubError:
                continue
            contributor_files.append(filename)
        return repository.model_copy(
            update={
                "has_release": has_release,
                "contributor_files": contributor_files,
            }
        )

    @staticmethod
    def _repository(item: dict[str, object]) -> GitHubRepository:
        license_data = item.get("license") or {}
        return GitHubRepository(
            full_name=item["full_name"],
            url=item["html_url"],
            description=item.get("description") or "",
            language=item.get("language"),
            topics=item.get("topics") or [],
            stars=item.get("stargazers_count", 0),
            forks=item.get("forks_count", 0),
            archived=item.get("archived", False),
            license_spdx=license_data.get("spdx_id"),
            created_at=item["created_at"],
            updated_at=item["updated_at"],
            pushed_at=item.get("pushed_at"),
            default_branch=item.get("default_branch") or "main",
        )

    @staticmethod
    def _issue(
        item: dict[str, object], repository: str | None = None
    ) -> GitHubIssue:
        repo = repository
        if repo is None:
            repository_url = str(item.get("repository_url", ""))
            repo = repository_url.removeprefix("https://api.github.com/repos/")
        labels = [
            label.get("name", "") if isinstance(label, dict) else str(label)
            for label in item.get("labels", [])
        ]
        return GitHubIssue(
            repository=repo or "",
            number=item["number"],
            title=item["title"],
            url=item["html_url"],
            body_excerpt=(item.get("body") or "")[:500],
            labels=[label for label in labels if label],
            comments=item.get("comments", 0),
            created_at=item["created_at"],
            updated_at=item["updated_at"],
        )
