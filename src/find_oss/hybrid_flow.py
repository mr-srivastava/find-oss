from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crewai import Agent
from crewai.flow.flow import Flow, start
from crewai_tools import GithubSearchTool
from pydantic import BaseModel, PrivateAttr

from find_oss.github_client import GitHubClient
from find_oss.hybrid_ranking import (
    is_semantic_enrichment_eligible,
    score_issue,
    score_repository,
)
from find_oss.llm_config import build_openai_llm
from find_oss.models import (
    ContributionCandidate,
    DiscoveryReport,
    Evidence,
    GitHubRepository,
    RunMetrics,
    SearchIntent,
    SemanticFinding,
    ToolCandidate,
)
from find_oss.ranking import rank_tools

MAX_ENRICHED_REPOSITORIES = 5

AgentKickoff = Callable[[str, str, type[Any]], Any]
SemanticSearch = Callable[[str, str], str]


class HybridFlowState(BaseModel):
    query: str = ""


class HybridDiscoveryFlow(Flow[HybridFlowState]):
    _llm_input_tokens: int = PrivateAttr(default=0)
    _llm_output_tokens: int = PrivateAttr(default=0)

    def __init__(
        self,
        *,
        client: GitHubClient,
        agent_kickoff: AgentKickoff | None = None,
        semantic_search: SemanticSearch | None = None,
    ) -> None:
        os.environ.setdefault(
            "CREWAI_STORAGE_DIR",
            str(Path(".find-oss/crewai-storage").resolve()),
        )
        os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
        super().__init__()
        self.client = client
        self.agent_kickoff = agent_kickoff or self._agent_kickoff
        self.semantic_search = semantic_search or self._semantic_search

    def run(self, query: str) -> DiscoveryReport:
        started = time.monotonic()
        intent = self.agent_kickoff(
            "intent",
            (
                "Normalize this open-source discovery request. Extract only explicit "
                "or strongly implied constraints. Return structured SearchIntent.\n\n"
                f"Request: {query}"
            ),
            SearchIntent,
        )
        repositories = []
        issues = []
        repository_queries = self._repository_queries(intent)
        repository_limit = max(1, 20 // len(repository_queries))
        for repository_query in repository_queries:
            repositories.extend(
                self.client.search_repositories(
                    repository_query, limit=repository_limit
                )
            )
        issue_queries = self._issue_queries(intent)
        issue_limit = max(1, 30 // len(issue_queries))
        for issue_query in issue_queries:
            issues.extend(self.client.search_issues(issue_query, limit=issue_limit))
        repositories = self._deduplicate_repositories(repositories)
        known_repositories = {item.full_name.lower() for item in repositories}
        for repository_name in list(
            dict.fromkeys(issue.repository for issue in issues)
        )[:10]:
            if repository_name.lower() not in known_repositories:
                repositories.append(self.client.get_repository(repository_name))
                known_repositories.add(repository_name.lower())
        repositories = [
            self.client.enrich_repository(repository)
            for repository in repositories
        ]
        scored = [
            (repository, score_repository(repository, intent))
            for repository in repositories
        ]
        scored.sort(key=lambda item: item[1].total, reverse=True)

        partial_failures: list[str] = []
        if not issues:
            partial_failures.append(
                "Issue search returned no results for: "
                + "; ".join(issue_queries)
            )
        semantic_findings: list[SemanticFinding] = []
        eligible = [
            item
            for item, _ in scored
            if is_semantic_enrichment_eligible(item, intent)
        ][:MAX_ENRICHED_REPOSITORIES]
        for repository in eligible:
            try:
                result = self.semantic_search(repository.full_name, intent.query)
                semantic_findings.append(
                    SemanticFinding(
                        repository=repository.full_name,
                        query=intent.query,
                        summary=result[:1500],
                    )
                )
            except Exception as error:
                partial_failures.append(
                    f"Semantic enrichment failed for {repository.full_name}: {error}"
                )

        tools = [
            self._tool_candidate(repository, scores, intent)
            for repository, scores in scored[:10]
        ]
        repository_map = {item.full_name.lower(): item for item in repositories}
        opportunities = []
        for issue in issues:
            repository = repository_map.get(issue.repository.lower())
            if repository is None:
                continue
            scores = score_issue(issue, repository, intent, datetime.now(timezone.utc))
            opportunities.append(
                ContributionCandidate(
                    repository=issue.repository,
                    issue_number=issue.number,
                    title=issue.title,
                    url=issue.url,
                    match_reason="Open issue matching the requested repository criteria.",
                    difficulty=(
                        "beginner-friendly"
                        if any(
                            label.lower()
                            in {"good first issue", "beginner", "documentation"}
                            for label in issue.labels
                        )
                        else "requires review"
                    ),
                    evidence=[
                        Evidence(claim="Open GitHub issue", url=issue.url),
                        Evidence(
                            claim="Repository metadata",
                            url=repository.url,
                        ),
                    ],
                    caveats=["Difficulty is inferred from labels and issue detail."],
                    scores=scores,
                    next_action="Read the issue and contribution guide before commenting.",
                )
            )
        opportunities.sort(key=lambda item: item.scores.total, reverse=True)

        compact_context = {
            "intent": intent.model_dump(mode="json"),
            "tools": [item.model_dump(mode="json") for item in tools],
            "opportunities": [
                item.model_dump(mode="json") for item in opportunities[:15]
            ],
            "semantic_findings": [
                item.model_dump(mode="json") for item in semantic_findings
            ],
            "partial_failures": partial_failures,
        }
        editorial = self.agent_kickoff(
            "report",
            (
                "Write a concise evidence-based summary for this structured OSS "
                "discovery result. Do not change scores or introduce facts. Return a "
                "DiscoveryReport; candidate arrays may be empty because authoritative "
                "candidates are supplied by the application.\n\n"
                + json.dumps(compact_context, separators=(",", ":"))
            ),
            DiscoveryReport,
        )
        metrics = RunMetrics(
            github_requests=self.client.metrics.request_count,
            cache_hits=self.client.metrics.cache_hits,
            semantic_searches=len(semantic_findings),
            llm_input_tokens=self._llm_input_tokens,
            llm_output_tokens=self._llm_output_tokens,
            elapsed_seconds=round(time.monotonic() - started, 3),
            partial_failures=partial_failures,
            rate_limit=self.client.rate_limit,
        )
        return DiscoveryReport(
            query=query,
            summary=editorial.summary,
            tools=rank_tools(tools, include_inactive=intent.include_inactive),
            opportunities=opportunities[:15],
            warnings=list(dict.fromkeys(editorial.warnings + partial_failures)),
            metrics=metrics,
        )

    @start()
    def discover(self) -> DiscoveryReport:
        return self.run(self.state.query)

    @staticmethod
    def _repository_query(intent: SearchIntent) -> str:
        parts = list(intent.topics)
        parts.extend(f"language:{item}" for item in intent.languages)
        parts.extend(f"license:{item}" for item in intent.licenses)
        if any(
            term in intent.query.lower()
            for term in ("good", "quality", "established", "popular")
        ):
            parts.append("stars:>=10")
        return " ".join(parts) or intent.query

    @classmethod
    def _repository_queries(cls, intent: SearchIntent) -> list[str]:
        if len(intent.languages) <= 1:
            return [cls._repository_query(intent)]
        return [
            cls._repository_query(intent.model_copy(update={"languages": [language]}))
            for language in intent.languages
        ]

    @staticmethod
    def _issue_query(intent: SearchIntent) -> str:
        parts = list(intent.topics)
        parts.extend(f"language:{item}" for item in intent.languages)
        if intent.experience_level and "begin" in intent.experience_level.lower():
            parts.append('label:"good first issue"')
        else:
            parts.append("label:help-wanted")
        return " ".join(parts) or intent.query

    @classmethod
    def _issue_queries(cls, intent: SearchIntent) -> list[str]:
        if len(intent.languages) <= 1:
            return [cls._issue_query(intent)]
        return [
            cls._issue_query(intent.model_copy(update={"languages": [language]}))
            for language in intent.languages
        ]

    @staticmethod
    def _deduplicate_repositories(
        repositories: list[GitHubRepository],
    ) -> list[GitHubRepository]:
        unique: dict[str, GitHubRepository] = {}
        for repository in repositories:
            unique.setdefault(repository.full_name.lower(), repository)
        return list(unique.values())

    @staticmethod
    def _tool_candidate(repository, scores, intent) -> ToolCandidate:
        caveats = []
        if not repository.license_spdx:
            caveats.append("No SPDX license was verified.")
        if repository.archived:
            caveats.append("Repository is archived.")
        return ToolCandidate(
            name=repository.full_name,
            url=repository.url,
            description=repository.description,
            match_reason="Repository metadata matches the normalized search constraints.",
            license=repository.license_spdx,
            archived=repository.archived,
            low_activity=scores.health < 5,
            evidence=[Evidence(claim="GitHub repository metadata", url=repository.url)],
            caveats=caveats,
            scores=scores,
            next_action="Review the README and contribution guidance.",
        )

    def _agent_kickoff(
        self, stage: str, prompt: str, response_format: type[Any]
    ) -> Any:
        agent = Agent(
            role="GitHub Open-Source Discovery Editor",
            goal="Normalize requests and explain verified GitHub evidence concisely.",
            backstory=(
                "You are a precise open-source researcher. You never invent project "
                "facts or numeric scores and clearly distinguish inference."
            ),
            llm=build_openai_llm(),
            reasoning=False,
            allow_delegation=False,
            max_iter=8,
            max_execution_time=120,
            verbose=False,
        )
        result = agent.kickoff(prompt, response_format=response_format)
        usage = result.usage_metrics
        self._llm_input_tokens += self._usage_value(
            usage, "prompt_tokens", "input_tokens"
        )
        self._llm_output_tokens += self._usage_value(
            usage, "completion_tokens", "output_tokens"
        )
        if result.pydantic is None:
            raise RuntimeError(f"{stage} agent returned malformed structured output.")
        return result.pydantic

    @staticmethod
    def _usage_value(usage: object, *names: str) -> int:
        for name in names:
            if isinstance(usage, dict):
                value = usage.get(name)
            else:
                value = getattr(usage, name, None)
            if value:
                return int(value)
        return 0

    @staticmethod
    def _semantic_search(repository: str, query: str) -> str:
        token = os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"]
        tool = GithubSearchTool(
            github_repo=f"https://github.com/{repository}",
            gh_token=token,
            content_types=["repo"],
            limit=5,
            max_usage_count=1,
        )
        return tool.run(search_query=query, limit=5)
