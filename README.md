# CV-agent

A Mistral Workflows agent that searches the web for job openings matching a candidate CV,
validates each fit, and emits a **parsable CSV** (plus the same data as JSON) for a downstream
agent to consume.

Each run:

1. Loads the packaged candidate profile and the selected CV variant.
2. Runs a web-search agent over company career pages, job boards, and public LinkedIn job
   postings/profiles.
3. Runs a second agent that re-opens every `source_url`, rewrites the fit justification, and
   drops postings it cannot verify.
4. Deterministically extracts a recruiter email / LinkedIn URL from the posting text, dedupes,
   ranks by `match_score`, and serializes to CSV.

LinkedIn is used **only through public web search results**. Nothing scrapes or automates
LinkedIn itself.

### Which API provides web search

Web search runs through the **Conversations API** (`client.beta.conversations.start_async`)
with a `WebSearchTool`. Two other paths do not work and should not be reintroduced:

| Path | Result |
| --- | --- |
| `Agent` + `RemoteSession` (Agents API) | `403 Creating agents is not available for this organization. Use Managed Agents instead.` |
| `chat.complete` with `tools=[{"type": "web_search"}]` | `400 WebSearchTool connector is not supported` |

The Agents API path also creates a remote agent per run and never deletes it, which would leak
one agent per scheduled execution. The Conversations API is stateless when called with
`store=False`, which is what this project uses.

If your organization *does* allow agent creation, the Conversations path still works — it is
not a downgrade.

## CSV schema

Columns are fixed and always in this order:

| Column | Meaning |
| --- | --- |
| `opening_id` | Stable 12-hex id (hash of position, company, source URL) — use it to dedupe across runs |
| `position` | Job title as advertised |
| `company` | Hiring company |
| `location` | Location as advertised |
| `description` | 2–3 sentence summary of the role |
| `validation_criteria` | Semicolon-separated, checkable reasons the opening fits the CV |
| `match_score` | Integer 0–100 fit estimate |
| `contact_kind` | `email`, `linkedin`, `url`, or `none` — where to go to act on the opening |
| `source_url` | Exact URL of the posting |
| `contact_email` | Recruiter/careers email, extracted from the posting when present |
| `linkedin_url` | LinkedIn posting/profile URL, extracted from the posting when present |
| `source` | `web`, `linkedin`, or `career_page` |
| `found_at` | UTC date, `YYYY-MM-DD` |

Every row is quoted (`QUOTE_ALL`), so commas, quotes, and newlines inside fields are safe to
parse with any RFC 4180 reader.

The JSON output wraps the same rows:

```json
{
  "schema_version": "1",
  "cv_variant": "forward_deployed",
  "generated_at": "2026-11-08T07:00:00+00:00",
  "count": 12,
  "openings": [ ... ],
  "csv": "opening_id,position,...\n..."
}
```

## Local run

```bash
uv sync --extra dev
export MISTRAL_API_KEY=...
mistral dev
```

`mistral dev` starts the worker locally. If the Mistral CLI is unavailable, the same worker can
be started directly:

```bash
uv run python -m worker.entrypoints.worker
```

Run the tests with `uv run pytest -q`.

### One-shot execution

With the worker running:

```python
from mistralai.client import Mistral
import os

client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
result = client.workflows.execute_workflow_and_wait(
    workflow_identifier="job-search",
    input={"cv_variant": "forward_deployed", "max_openings": 5},
)
print(result["csv"])
```

Input fields: `cv_variant` (`forward_deployed` or `industry`), `max_openings` (1–50), and an
optional `profile_override` object merged over the packaged profile.

## Deploy

```bash
cv-agent-deploy --name cv-agent --repo https://github.com/<owner>/CV-agent
```

This creates a Mistral managed deployment that builds the repository's `Dockerfile`. The
deployment reaches `Active` once the image builds. To redeploy an existing deployment:

```bash
cv-agent-deploy --name cv-agent --repo https://github.com/<owner>/CV-agent --restart
```

The repository must be reachable by the Mistral GitHub App.

## Schedule

```bash
cv-agent-schedule --deployment cv-agent
```

Defaults to `0 7 * * 1,4` (Mondays and Thursdays, 07:00 UTC), CV variant `forward_deployed`, and
`max_openings=15`. Overlap policy is *skip* — a run still in flight is not stacked — and the
catch-up window is one day, so an outage does not replay a week of stale searches.

```bash
cv-agent-schedule --list
cv-agent-schedule --delete <schedule_id>
```

## Fetch results

```bash
cv-agent-fetch --latest          # most recent completed run
cv-agent-fetch --execution-id <id>
```

Writes `out/job-search-<date>.csv` and `out/job-search-<date>.json`. Use `--out-dir` to change
the destination.

## Layout

```
src/worker/
  candidate_data/     packaged profile.yaml and CV variants
  entrypoints/        worker bootstrap
  workflows/
    job_search.py     workflow definition (orchestration only)
    activities.py     all I/O, model calls, and serialization
    contacts.py       deterministic email / LinkedIn extraction
    serialization.py  dedupe, ranking, CSV
    models.py         pydantic input/output schema
  cli/                deploy, schedule, fetch
```
