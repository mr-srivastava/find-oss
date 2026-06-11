from pathlib import Path
from types import SimpleNamespace

import pytest

from find_oss.models import DiscoveryReport
from find_oss.github_client import (
    GitHubAuthenticationError,
    GitHubRateLimitError,
)
from find_oss.service import run_search, validate_environment


def test_environment_requires_openai_and_github_tokens() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        validate_environment({})
    with pytest.raises(ValueError, match="GITHUB_PERSONAL_ACCESS_TOKEN"):
        validate_environment({"OPENAI_API_KEY": "openai"})


def test_search_writes_valid_partial_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = DiscoveryReport(
        query="Find tools",
        summary="Only tool matches were credible.",
    )
    monkeypatch.setattr(
        "find_oss.service._kickoff",
        lambda query: SimpleNamespace(pydantic=report),
    )
    monkeypatch.setattr(
        "find_oss.service.validate_environment",
        lambda environment=None: ("openai", "github"),
    )

    result = run_search("Find tools", tmp_path)

    assert result.output_path.exists()
    assert "No credible contribution opportunities" in result.output_path.read_text()
    assert any("issue" in warning.lower() for warning in result.report.warnings)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (GitHubAuthenticationError("failed"), "authentication failed"),
        (GitHubRateLimitError("failed"), "rate limit reached"),
        ("Failed to connect to OpenAI API: Request timed out", "OpenAI request timed out"),
    ],
)
def test_search_translates_github_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    message: object,
    expected: str,
) -> None:
    def fail(query: str) -> object:
        if isinstance(message, Exception):
            raise message
        raise Exception(message)

    monkeypatch.setattr("find_oss.service._kickoff", fail)
    monkeypatch.setattr(
        "find_oss.service.validate_environment",
        lambda environment=None: ("openai", "github"),
    )

    with pytest.raises(RuntimeError, match=expected):
        run_search("Find tools", tmp_path)


def test_search_rejects_malformed_structured_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "find_oss.service._kickoff",
        lambda query: SimpleNamespace(raw="not json"),
    )
    monkeypatch.setattr(
        "find_oss.service.validate_environment",
        lambda environment=None: ("openai", "github"),
    )

    with pytest.raises(RuntimeError, match="malformed structured report"):
        run_search("Find tools", tmp_path)
