# Find OSS

Find OSS is a local CrewAI application that finds open-source tools and
contribution opportunities from a natural-language request. It combines
bounded GitHub API searches with selective semantic repository search, ranks
the results, cites GitHub evidence, and writes a Markdown report.

The GitHub integration is read-only. Find OSS exposes only search and
inspection operations and doesn't require Docker.

## How discovery works

Find OSS uses a hybrid retrieval flow to control cost and report quality:

1. One structured OpenAI call converts your request into search constraints.
2. Custom CrewAI tools query the GitHub REST API for compact repository and
   open-issue metadata.
3. Python deduplicates, filters, scores, and shortlists the results.
4. CrewAI's `GithubSearchTool` semantically inspects at most five shortlisted
   repositories when repository documentation needs more context.
5. One structured OpenAI call writes the concise report summary.

The application doesn't send raw GitHub responses, complete issue timelines,
commit histories, or full repository trees to the model. Numeric scores come
from deterministic Python rules rather than the model.

## Requirements

Install the following software and credentials:

- Python 3.10 through 3.13
- [uv](https://docs.astral.sh/uv/)
- A GitHub fine-grained personal access token with read-only access
- An OpenAI API key

Docker and the GitHub MCP server aren't required.

## Install

Install the project and development dependencies:

```bash
uv sync --all-groups
```

Create a `.env` file:

```dotenv
MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=your-openai-api-key
GITHUB_PERSONAL_ACCESS_TOKEN=your-read-only-github-token
```

Don't grant write permissions to the GitHub token. Find OSS doesn't need them.
The `.env` file is ignored by Git.

## Search

Run a unified search for tools and contribution opportunities:

```bash
uv run find_oss search \
  "Find self-hosted Python AI coding tools and beginner issues for a weekend"
```

The command prints a count and report path. Reports are stored under `output/`
with a UTC timestamp and a query-derived slug.

Each report contains:

- Ranked open-source tools
- Ranked contribution opportunities
- GitHub evidence links
- Deterministic score breakdowns, caveats, and suggested next actions
- Explicit messages when either section has no credible matches
- Request, semantic-search, token, latency, and rate-limit metrics

## Token and request controls

Each run uses these default ceilings:

- 20 repository search candidates
- 30 open-issue search candidates
- 5 semantically enriched repositories
- 5 semantic results per repository
- 2 structured agent calls

Identical GitHub reads are cached within a run. Semantic-search failures produce
warnings and don't discard candidates supported by GitHub API evidence.

## Save searches

Saved searches store reusable natural-language queries. Version 1 supports
manual reruns only.

```bash
uv run find_oss save "Weekend AI" \
  "Find beginner-friendly Python AI agent issues I can finish this weekend"

uv run find_oss saved list
uv run find_oss saved run "weekend-ai"
uv run find_oss saved update "weekend-ai" \
  "Find beginner-friendly TypeScript AI agent issues"
uv run find_oss saved delete "weekend-ai"
```

Find OSS stores saved searches in `.find-oss/saved-searches.yaml`. Each entry
contains a schema version, display name, stable slug, query, creation time, and
update time. Writes replace the file atomically.

Use `--store PATH` to select another saved-search file and `--output-dir PATH`
to select another report directory:

```bash
uv run find_oss --store searches/team.yaml --output-dir reports \
  saved run "weekend-ai"
```

## Reliability and privacy

Find OSS distinguishes GitHub authentication, permissions, validation, rate
limits, network failures, OpenAI timeouts, and malformed structured output.
Errors don't print credentials.

OpenAI requests use a 90-second timeout and three SDK retries. CrewAI telemetry
is disabled by default. CrewAI runtime storage stays under
`.find-oss/crewai-storage/`.

## Development

Run the automated checks:

```bash
uv run pytest
uv run ruff check .
```

A live smoke search requires valid GitHub and OpenAI credentials and network
access.
