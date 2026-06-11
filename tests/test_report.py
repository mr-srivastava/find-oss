from collections.abc import Callable

from find_oss.models import DiscoveryReport, ScoreBreakdown, ToolCandidate
from find_oss.report import render_report


def test_empty_report_states_no_credible_matches(
    report_factory: Callable[..., DiscoveryReport],
) -> None:
    markdown = render_report(report_factory())

    assert "## Open-Source Tools" in markdown
    assert "No credible tool matches were found." in markdown
    assert "## Contribution Opportunities" in markdown
    assert "No credible contribution opportunities were found." in markdown


def test_unknown_license_is_rendered_as_a_caveat(
    report_factory: Callable[..., DiscoveryReport],
) -> None:
    report = report_factory(
        tools=[
            ToolCandidate(
                name="Example",
                url="https://github.com/example/project",
                match_reason="It matches.",
                scores=ScoreBreakdown(
                    relevance=8,
                    health=7,
                    maturity=6,
                    license=0,
                    accessibility=8,
                ),
            )
        ],
    )

    markdown = render_report(report)

    assert "No license was verified" in markdown
