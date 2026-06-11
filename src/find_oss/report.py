from __future__ import annotations

from find_oss.models import (
    ContributionCandidate,
    DiscoveryReport,
    ScoreBreakdown,
    ToolCandidate,
)


def _score_line(scores: ScoreBreakdown) -> str:
    return (
        f"**Score:** {scores.total}/10 "
        f"(relevance {scores.relevance}, health {scores.health}, "
        f"maturity {scores.maturity}, license {scores.license}, "
        f"accessibility {scores.accessibility})"
    )


def _tool_section(item: ToolCandidate, index: int) -> list[str]:
    lines = [
        f"### {index}. [{item.name}]({item.url})",
        item.description or item.match_reason,
        "",
        f"**Why it matches:** {item.match_reason}",
        _score_line(item.scores),
    ]
    if item.evidence:
        lines.append(
            "**Evidence:** "
            + "; ".join(f"[{e.claim}]({e.url})" for e in item.evidence)
        )
    caveats = list(item.caveats)
    if not item.license:
        caveats.append(
            "No license was verified; review the repository before reuse or "
            "contribution."
        )
    if caveats:
        lines.append("**Caveats:** " + "; ".join(dict.fromkeys(caveats)))
    if item.next_action:
        lines.append(f"**Next action:** {item.next_action}")
    return lines


def _opportunity_section(
    item: ContributionCandidate, index: int
) -> list[str]:
    lines = [
        f"### {index}. [{item.repository} #{item.issue_number}: "
        f"{item.title}]({item.url})",
        f"**Why it matches:** {item.match_reason}",
        _score_line(item.scores),
    ]
    if item.difficulty:
        lines.append(f"**Estimated difficulty:** {item.difficulty} (inferred)")
    if item.evidence:
        lines.append(
            "**Evidence:** "
            + "; ".join(f"[{e.claim}]({e.url})" for e in item.evidence)
        )
    if item.caveats:
        lines.append("**Caveats:** " + "; ".join(item.caveats))
    if item.next_action:
        lines.append(f"**Next action:** {item.next_action}")
    return lines


def render_report(report: DiscoveryReport) -> str:
    lines = [
        "# Open-Source Discovery Report",
        "",
        f"**Query:** {report.query}",
        "",
        report.summary,
        "",
        "## Open-Source Tools",
        "",
    ]
    if report.tools:
        for index, item in enumerate(report.tools, start=1):
            lines.extend(_tool_section(item, index))
            lines.append("")
    else:
        lines.extend(["No credible tool matches were found.", ""])

    lines.extend(["## Contribution Opportunities", ""])
    if report.opportunities:
        for index, item in enumerate(report.opportunities, start=1):
            lines.extend(_opportunity_section(item, index))
            lines.append("")
    else:
        lines.extend(["No credible contribution opportunities were found.", ""])

    if report.warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in report.warnings)
        lines.append("")
    if report.metrics:
        metrics = report.metrics
        lines.extend(
            [
                "## Run Metrics",
                "",
                f"- GitHub requests: {metrics.github_requests}",
                f"- In-run cache hits: {metrics.cache_hits}",
                f"- Semantic searches: {metrics.semantic_searches}",
                f"- LLM input tokens: {metrics.llm_input_tokens}",
                f"- LLM output tokens: {metrics.llm_output_tokens}",
                f"- Elapsed seconds: {metrics.elapsed_seconds}",
            ]
        )
        if metrics.rate_limit and metrics.rate_limit.remaining is not None:
            lines.append(
                f"- GitHub search requests remaining: "
                f"{metrics.rate_limit.remaining}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
