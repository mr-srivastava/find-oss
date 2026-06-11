from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from find_oss.github_client import (
    GitHubAuthenticationError,
    GitHubClient,
    GitHubNetworkError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubValidationError,
)
from find_oss.models import DiscoveryReport
from find_oss.ranking import (
    deduplicate_contributions,
    deduplicate_tools,
    rank_tools,
)
from find_oss.report import render_report


@dataclass(frozen=True)
class SearchRunResult:
    report: DiscoveryReport
    output_path: Path

    @property
    def summary(self) -> str:
        return (
            f"Found {len(self.report.tools)} tools and "
            f"{len(self.report.opportunities)} contribution opportunities."
        )


def _query_slug(query: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    return slug[:60].rstrip("-") or "search"


def _extract_report(output: object) -> DiscoveryReport:
    if isinstance(output, DiscoveryReport):
        return output
    pydantic_output = getattr(output, "pydantic", None)
    if isinstance(pydantic_output, DiscoveryReport):
        return pydantic_output
    raw = getattr(output, "raw", None)
    if isinstance(raw, str):
        try:
            return DiscoveryReport.model_validate_json(raw)
        except ValueError as error:
            raise RuntimeError(
                "CrewAI returned a malformed structured report."
            ) from error
    raise RuntimeError("CrewAI did not return a structured discovery report.")


def _kickoff(query: str) -> object:
    from find_oss.hybrid_flow import HybridDiscoveryFlow

    token = os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"]
    return HybridDiscoveryFlow(client=GitHubClient(token)).run(query)


def validate_environment(
    environment: dict[str, str] | os._Environ[str] | None = None,
) -> tuple[str, str]:
    values = environment if environment is not None else os.environ
    openai_token = values.get("OPENAI_API_KEY", "").strip()
    if not openai_token:
        raise ValueError("OPENAI_API_KEY is required.")
    github_token = values.get("GITHUB_PERSONAL_ACCESS_TOKEN", "").strip()
    if not github_token:
        raise ValueError(
            "GITHUB_PERSONAL_ACCESS_TOKEN is required; use a read-only token."
        )
    return openai_token, github_token


def run_search(query: str, output_dir: Path) -> SearchRunResult:
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("Search query cannot be empty.")
    validate_environment()
    try:
        output = _kickoff(normalized_query)
    except GitHubAuthenticationError as error:
        raise RuntimeError(
            "GitHub authentication failed. Check the read-only token."
        ) from error
    except GitHubPermissionError as error:
        raise RuntimeError(
            "GitHub token lacks required read permissions."
        ) from error
    except GitHubRateLimitError as error:
        raise RuntimeError(
            "GitHub rate limit reached. Retry after the limit resets."
        ) from error
    except GitHubValidationError as error:
        raise RuntimeError(
            "GitHub rejected the generated search query."
        ) from error
    except GitHubNetworkError as error:
        raise RuntimeError(
            "GitHub API is unavailable. Check your connection and retry."
        ) from error
    except Exception as error:
        message = str(error).lower()
        if "timed out" in message or "timeout" in message:
            raise RuntimeError(
                "OpenAI request timed out after retries. Check your connection "
                "and rerun the search."
            ) from error
        raise RuntimeError(f"Discovery flow failed: {error}") from error

    report = _extract_report(output)
    include_inactive = (
        "archived" in normalized_query.lower()
        or "inactive" in normalized_query.lower()
    )
    report.tools = rank_tools(
        deduplicate_tools(report.tools), include_inactive=include_inactive
    )
    report.opportunities = sorted(
        deduplicate_contributions(report.opportunities),
        key=lambda item: item.scores.total,
        reverse=True,
    )
    if not report.opportunities and not any(
        "issue search" in warning.lower() for warning in report.warnings
    ):
        report.warnings.append(
            "No contribution opportunities matched the searched repositories "
            "and issue criteria."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_path = output_dir / f"{timestamp}-{_query_slug(normalized_query)}.md"
    output_path.write_text(render_report(report), encoding="utf-8")
    return SearchRunResult(report=report, output_path=output_path)
