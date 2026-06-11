from __future__ import annotations

from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from find_oss.github_client import GitHubClient

READ_ONLY_TOOL_NAMES = (
    "search_github_repositories",
    "search_open_github_issues",
    "get_github_repository_metadata",
    "get_github_issue_details",
    "inspect_github_rate_limit",
)


class SearchInput(BaseModel):
    query: str = Field(description="GitHub search query")
    limit: int = Field(default=10, ge=1)


class RepositoryInput(BaseModel):
    full_name: str = Field(description="Repository in owner/name form")


class IssueInput(BaseModel):
    repository: str = Field(description="Repository in owner/name form")
    number: int = Field(ge=1)


class EmptyInput(BaseModel):
    pass


class GitHubClientTool(BaseTool):
    _client: GitHubClient = PrivateAttr()

    def __init__(self, client: GitHubClient, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._client = client


class RepositorySearchTool(GitHubClientTool):
    name: str = "search_github_repositories"
    description: str = "Search public GitHub repositories with a maximum of 20 results."
    args_schema: Type[BaseModel] = SearchInput

    def _run(self, query: str, limit: int = 10) -> str:
        results = self._client.search_repositories(query, limit=limit)
        return BaseModelList(items=results).model_dump_json()


class IssueSearchTool(GitHubClientTool):
    name: str = "search_open_github_issues"
    description: str = "Search open GitHub issues with a maximum of 30 results."
    args_schema: Type[BaseModel] = SearchInput

    def _run(self, query: str, limit: int = 10) -> str:
        results = self._client.search_issues(query, limit=limit)
        return BaseModelList(items=results).model_dump_json()


class RepositoryMetadataTool(GitHubClientTool):
    name: str = "get_github_repository_metadata"
    description: str = "Read compact authoritative metadata for one GitHub repository."
    args_schema: Type[BaseModel] = RepositoryInput

    def _run(self, full_name: str) -> str:
        return self._client.get_repository(full_name).model_dump_json()


class IssueDetailsTool(GitHubClientTool):
    name: str = "get_github_issue_details"
    description: str = "Read compact details for one GitHub issue."
    args_schema: Type[BaseModel] = IssueInput

    def _run(self, repository: str, number: int) -> str:
        return self._client.get_issue(repository, number).model_dump_json()


class RateLimitTool(GitHubClientTool):
    name: str = "inspect_github_rate_limit"
    description: str = "Read the current GitHub API search rate-limit state."
    args_schema: Type[BaseModel] = EmptyInput

    def _run(self) -> str:
        return self._client.get_rate_limit().model_dump_json()


class BaseModelList(BaseModel):
    items: list[BaseModel]


def build_github_tools(
    token: str, *, client: GitHubClient | None = None
) -> list[BaseTool]:
    github = client or GitHubClient(token)
    return [
        RepositorySearchTool(github),
        IssueSearchTool(github),
        RepositoryMetadataTool(github),
        IssueDetailsTool(github),
        RateLimitTool(github),
    ]
