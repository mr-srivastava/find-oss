from collections.abc import Callable
from types import SimpleNamespace

from find_oss.hybrid_flow import HybridDiscoveryFlow
from find_oss.models import (
    DiscoveryReport,
    GitHubIssue,
    GitHubRepository,
    SearchIntent,
)


class FakeClient:
    def __init__(
        self,
        repository_factory: Callable[..., GitHubRepository],
        issue_factory: Callable[..., GitHubIssue],
        *,
        repositories: list[GitHubRepository] | None = None,
        issues: list[GitHubIssue] | None = None,
    ) -> None:
        self.repository_factory = repository_factory
        self.repositories = repositories
        self.issues = issues
        self.repository_queries: list[str] = []
        self.issue_queries: list[str] = []
        self.metrics = SimpleNamespace(request_count=2, cache_hits=0)
        self.rate_limit = None
        self.default_issue = issue_factory()

    def search_repositories(self, query, limit=20):
        self.repository_queries.append(query)
        return self.repositories or [
            self.repository_factory(index, contributor_files=[]) for index in range(8)
        ]

    def search_issues(self, query, limit=30):
        self.issue_queries.append(query)
        return [self.default_issue] if self.issues is None else self.issues

    def get_repository(self, full_name):
        index = int(full_name.rsplit("-", 1)[-1])
        return self.repository_factory(index)

    def enrich_repository(self, repository):
        return repository.model_copy(
            update={"contributor_files": ["CONTRIBUTING.md"], "has_release": True}
        )


def test_flow_returns_ranked_candidates_with_bounded_semantic_searches(
    repository_factory: Callable[..., GitHubRepository],
    issue_factory: Callable[..., GitHubIssue],
    report_factory: Callable[..., DiscoveryReport],
) -> None:
    enriched: list[str] = []

    def kickoff(stage, prompt, response_format):
        if stage == "intent":
            return SearchIntent(
                query="Explain the architecture of Python agents",
                languages=["Python"],
                topics=["agents"],
            )
        return report_factory(query="Find Python agents")

    flow = HybridDiscoveryFlow(
        client=FakeClient(repository_factory, issue_factory),
        agent_kickoff=kickoff,
        semantic_search=lambda repository, query: enriched.append(repository)
        or "semantic result",
    )

    report = flow.run("Find Python agents")

    assert len(enriched) == 5
    assert report.metrics.semantic_searches == 5
    assert report.tools
    assert report.opportunities


def test_semantic_failure_preserves_api_candidates(
    repository_factory: Callable[..., GitHubRepository],
    issue_factory: Callable[..., GitHubIssue],
    report_factory: Callable[..., DiscoveryReport],
) -> None:
    def kickoff(stage, prompt, response_format):
        if stage == "intent":
            return SearchIntent(
                query="Explain agent architecture", topics=["agents"]
            )
        return report_factory()

    flow = HybridDiscoveryFlow(
        client=FakeClient(repository_factory, issue_factory),
        agent_kickoff=kickoff,
        semantic_search=lambda repository, query: (_ for _ in ()).throw(
            RuntimeError("index failed")
        ),
    )

    report = flow.run("Find agents")

    assert report.tools
    assert report.metrics.partial_failures
    assert "Semantic enrichment failed" in report.metrics.partial_failures[0]


def test_report_prompt_contains_compact_models_not_raw_payloads(
    repository_factory: Callable[..., GitHubRepository],
    issue_factory: Callable[..., GitHubIssue],
    report_factory: Callable[..., DiscoveryReport],
) -> None:
    prompts: list[str] = []

    def kickoff(stage, prompt, response_format):
        prompts.append(prompt)
        if stage == "intent":
            return SearchIntent(query="Find agents")
        return report_factory()

    HybridDiscoveryFlow(
        client=FakeClient(repository_factory, issue_factory),
        agent_kickoff=kickoff,
        semantic_search=lambda repository, query: "short finding",
    ).run("Find agents")

    assert "ignored_large_field" not in prompts[-1]
    assert len(prompts[-1]) < 25_000


def test_crewai_flow_kickoff_accepts_query_input(
    repository_factory: Callable[..., GitHubRepository],
    issue_factory: Callable[..., GitHubIssue],
    report_factory: Callable[..., DiscoveryReport],
) -> None:
    def kickoff(stage, prompt, response_format):
        if stage == "intent":
            return SearchIntent(query="Find agents")
        return report_factory()

    result = HybridDiscoveryFlow(
        client=FakeClient(repository_factory, issue_factory),
        agent_kickoff=kickoff,
        semantic_search=lambda repository, query: "finding",
    ).kickoff(inputs={"query": "Find agents"})

    assert isinstance(result, DiscoveryReport)


def test_multilanguage_intent_runs_separate_searches(
    repository_factory: Callable[..., GitHubRepository],
    issue_factory: Callable[..., GitHubIssue],
    report_factory: Callable[..., DiscoveryReport],
) -> None:
    client = FakeClient(
        repository_factory,
        issue_factory,
        repositories=[repository_factory()],
        issues=[],
    )
    def kickoff(stage, prompt, response_format):
        if stage == "intent":
            return SearchIntent(
                query="Find TypeScript or JavaScript projects",
                languages=["TypeScript", "JavaScript"],
            )
        return report_factory()

    HybridDiscoveryFlow(
        client=client,
        agent_kickoff=kickoff,
        semantic_search=lambda repository, query: "finding",
    ).run("Find TypeScript or JavaScript projects")

    assert client.repository_queries == ["language:TypeScript", "language:JavaScript"]
    assert client.issue_queries == [
        "language:TypeScript label:help-wanted",
        "language:JavaScript label:help-wanted",
    ]


def test_issue_repository_is_hydrated_when_absent_from_repository_search(
    repository_factory: Callable[..., GitHubRepository],
    issue_factory: Callable[..., GitHubIssue],
    report_factory: Callable[..., DiscoveryReport],
) -> None:
    client = FakeClient(
        repository_factory,
        issue_factory,
        repositories=[repository_factory()],
        issues=[
            issue_factory(
                repository="acme/project-9",
                number=9,
                url="https://github.com/acme/project-9/issues/9",
                labels=["help wanted"],
            )
        ],
    )
    def kickoff(stage, prompt, response_format):
        if stage == "intent":
            return SearchIntent(query="Find projects")
        return report_factory(query="Find projects")

    report = HybridDiscoveryFlow(
        client=client,
        agent_kickoff=kickoff,
        semantic_search=lambda repository, query: "finding",
    ).run("Find projects")

    assert report.opportunities[0].repository == "acme/project-9"


def test_empty_issue_search_reports_queries_attempted(
    repository_factory: Callable[..., GitHubRepository],
    issue_factory: Callable[..., GitHubIssue],
    report_factory: Callable[..., DiscoveryReport],
) -> None:
    def kickoff(stage, prompt, response_format):
        if stage == "intent":
            return SearchIntent(query="Find TypeScript projects", languages=["TypeScript"])
        return report_factory()

    result = HybridDiscoveryFlow(
        client=FakeClient(repository_factory, issue_factory, issues=[]),
        agent_kickoff=kickoff,
        semantic_search=lambda repository, query: "finding",
    ).run("Find TypeScript projects")

    assert any("Issue search returned no results" in item for item in result.warnings)


def test_good_project_query_adds_quality_floor(
    repository_factory: Callable[..., GitHubRepository],
    issue_factory: Callable[..., GitHubIssue],
    report_factory: Callable[..., DiscoveryReport],
) -> None:
    client = FakeClient(
        repository_factory,
        issue_factory,
        repositories=[repository_factory()],
        issues=[],
    )

    def kickoff(stage, prompt, response_format):
        if stage == "intent":
            return SearchIntent(
                query="Find good TypeScript projects",
                languages=["TypeScript"],
            )
        return report_factory()

    HybridDiscoveryFlow(
        client=client,
        agent_kickoff=kickoff,
        semantic_search=lambda repository, query: "finding",
    ).run("Find good TypeScript projects")

    assert client.repository_queries == ["language:TypeScript stars:>=10"]
