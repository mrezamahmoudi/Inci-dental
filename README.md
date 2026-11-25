# Inci-dental 🦷

> **Incident management that gets to the root of the tooth.**

Incidents are like cavities: ignore them and they only get worse. **Inci-dental**
helps your team triage, page, and resolve incidents before they turn into a
full-blown root canal. Built for on-call engineers who'd rather be sleeping than
drilling into logs at 3 AM.

## Why "Inci-dental"?

Because every incident has a **root cause** — and like a tooth, if you don't get
to the root, it's going to hurt again. Inci-dental drills down so you don't have
to. Floss your alerts, brush up your runbooks, and keep your uptime cavity-free.

## Features

- 🦷 **Triage** — surface the painful incidents first, before they decay into P1s
- 🪥 **Paging** — nag the on-call until the cavity is filled (no drill required)
- 🔍 **Root-cause tracking** — because treating the symptom is just a temporary filling
- 📋 **Postmortems** — document the damage; learn why the tooth ached
- 🧾 **Runbooks** — step-by-step guides, so nobody has to wing the extraction

A small, general-purpose incident-management API that **automatically creates a
Mattermost group for every incident** and sends all related messages to it.

Built with FastAPI and public REST APIs via `httpx`. Chat, reporting, and action
tracking are selected by configuration. Mattermost, Confluence, Jira, and GitLab
are supported; no private/internal SDK or fixed company installation is required.

## What it does

- Starts one incident at a time and creates a uniquely named incident channel.
- Adds configured initial members to the new channel.
- Sends start, responder-review, periodic reminder, and end messages to that
  channel.
- Persists the active incident and channel identity across restarts.
- Creates templated incident reports in Confluence Cloud or GitLab Wiki.
- Creates assigned, prioritized actions in Jira or GitLab linked to a verified report.
- Protects state-changing endpoints with a bearer API key.
- Exposes health and Prometheus metrics endpoints.

It deliberately does **not** include city migration, load/auto shedding, ride
simulation, shift delivery, automatic group-membership updates, company
on-call/directory APIs, or any other organization-specific automation.

## Quick start

Requires Python 3.11+ and Mattermost. Reporting/action providers are optional;
configure only the providers you select. Private/self-hosted Jira and GitLab are
supported. See [Provider configuration](docs/providers.md).

```bash
cp .env.example .env
# Replace every example value in .env.
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=app uvicorn HttpHandler.api:create_app --factory --reload
```

Open <http://localhost:8000/docs> for interactive API documentation.

```bash
curl -X POST http://localhost:8000/api/v1/incidents \
  -H 'Authorization: Bearer your-api-key' \
  -H 'X-Actor: your-operator-name' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Database latency"}'
```

The response includes the newly created `channel_name` and `channel_url`.

```bash
curl http://localhost:8000/api/v1/incidents/current

curl -X POST http://localhost:8000/api/v1/incidents/current/end \
  -H 'Authorization: Bearer your-api-key' \
  -H 'X-Actor: your-operator-name'
```

## API

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/incidents` | Bearer | Create a group and start an incident. |
| `GET` | `/api/v1/incidents/current` | No | Read the current incident and group. |
| `POST` | `/api/v1/incidents/current/end` | Bearer | Announce and end the active incident. |
| `POST` | `/api/v1/incident-reports` | Bearer | Create a report in the selected provider. |
| `POST` | `/api/v1/actions` | Bearer | Create and assign an action linked to a report. |
| `GET` | `/healthz` | No | Liveness/readiness response. |
| `GET` | `/metrics` | No | Prometheus metrics. |
| `GET` | `/docs` | No | OpenAPI documentation. |

A second start while active returns `409`. Ending with no active incident also
returns `409`. Group-creation or end-notification failures return `502`.
Invalid titles and missing configuration are rejected.

If an end notification fails, the incident stays active so the request can be
retried. If a start notification fails after group creation, the incident stays
active and its group is retained; check the logs and Mattermost connectivity.

### Incident reports

`POST /api/v1/incident-reports` creates a Confluence page or GitLab Wiki page,
depending on `REPORT_PROVIDER`:

```json
{
  "title": "Database outage",
  "summary": "The primary database became unavailable.",
  "impact": "Users could not sign in for 15 minutes.",
  "root_cause": "The automatic failover did not complete.",
  "timeline": "12:00 UTC detected\n12:15 UTC service restored",
  "resolution": "Promoted the healthy replica."
}
```

The template contains summary, impact, root cause, timeline, resolution, and
follow-up sections. Its response includes `provider`, `report_id`, `title`, and `url`.
Reports are explicit post-incident actions, not an extra failure point in the
incident start/end flow.

### Action items

Use the returned `report_id` to create an action for the current on-call person:

```json
{
  "description": "Add a saturation alert and test automatic failover.",
  "assignee": "jira-account-id",
  "priority": "High",
  "related_report_id": "123456",
  "title": "Improve database failover"
}
```

`title` is optional and defaults to the description's first line. The meaning of
`assignee` follows the configured provider: Jira Data Center username, Jira Cloud
accountId, or GitLab username. Jira uses its native priority; GitLab maps the
value to a `priority::<value>` label. The endpoint verifies the report, creates
and assigns the action, and links it to the report. It returns `issue_key`,
`url`, and link information. A missing report returns `404`; an unconfigured or
disabled provider returns `503`; upstream provider failures return `502`.

Set `related_report_provider` only when the report was created in a non-default
provider. For example, `ACTION_PROVIDER=jira` can link a Jira issue to a report
created with `REPORT_PROVIDER=gitlab`; the canonical report URL is preserved.

The caller supplies the assignee, so this flow does not require an internal
on-call service. An on-call scheduler can call this endpoint after selecting the
current responder.

## Configuration

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `CHAT_PROVIDER` | No | `mattermost` | Incident group provider. |
| `REPORT_PROVIDER` | No | `none` | `confluence`, `gitlab`, or `none`. |
| `ACTION_PROVIDER` | No | `none` | `jira`, `gitlab`, or `none`. |
| `MATTERMOST_URL` | Yes | — | Mattermost base URL, e.g. `https://mattermost.example.com`. |
| `MATTERMOST_API_TOKEN` | Yes | — | Personal access token; never commit it. |
| `MATTERMOST_TEAM_ID` | Yes | — | ID of the team that owns incident channels. |
| `INCIDENT_API_KEY` | Yes | — | Bearer key for start/end requests. |
| `INCIDENT_CHANNEL_PREFIX` | No | `incident` | Prefix for generated channel names. |
| `MATTERMOST_PRIVATE_CHANNELS` | No | `true` | `true` for private, `false` for public channels. |
| `INCIDENT_INITIAL_MEMBERS` | No | empty | Comma-separated Mattermost user emails added at creation. |
| `INCIDENT_RESPONDERS` | No | empty | Comma-separated names or `@mentions` in the service-review message. |
| `ONCALL_URL` | No | empty | Public or self-hosted on-call schedule link in the start message. |
| `INCIDENT_STATE_FILE` | No | `/data/incident-state.json` | Atomic JSON state-file path. |
| `INCIDENT_REMINDER_INTERVAL_SECONDS` | No | `1800` | Seconds between active-incident reminders. |
| `LOG_LEVEL` | No | `INFO` | Standard Python logging level. |
| `PORT` | No | `8000` | Listening port when running `app/main.py`. |
| `CONFLUENCE_URL` | If selected | — | Confluence Cloud base URL, e.g. `https://your-site.atlassian.net`. |
| `CONFLUENCE_EMAIL` | If selected | — | Email for Confluence Cloud basic authentication. |
| `CONFLUENCE_API_TOKEN` | If selected | — | Confluence Cloud API token; never commit it. |
| `CONFLUENCE_SPACE_ID` | If selected | — | Numeric Confluence space ID, not the space key. |
| `CONFLUENCE_PARENT_PAGE_ID` | No | empty | Optional numeric parent page ID for reports. |
| `JIRA_URL` | If selected | — | Private Jira or Jira Cloud base URL, without `/rest/api/...`. |
| `JIRA_CLOUD` | No | `false` | `false` for private/Data Center; `true` for Cloud. |
| `JIRA_EMAIL` | Cloud | empty | Required only for Jira Cloud basic authentication. |
| `JIRA_API_TOKEN` | If selected | — | Jira Cloud API token or private Jira personal token. |
| `JIRA_PROJECT_KEY` | If selected | — | Jira project key, for example `INC`. |
| `JIRA_ISSUE_TYPE` | No | `Task` | Existing Jira issue type for incident actions. |
| `GITLAB_URL` | If selected | — | SaaS or private GitLab base URL. |
| `GITLAB_TOKEN` | If selected | — | GitLab access token with API scope. |
| `GITLAB_PROJECT_ID` | If selected | — | Numeric project ID or `namespace/project` path. |

`X-Actor` is an optional audit label. It is not an authenticated user identity;
use a trusted reverse proxy if named-user authentication is required.

The Mattermost token needs permission to create channels in the configured team,
resolve users by email, add channel members, and create posts. Use a dedicated
bot/service account with the least permissions your server allows.

Confluence credentials need permission to read and create pages in the
configured space. Jira credentials need Browse Projects, Create Issues, Assign
Issues, and permission to add remote issue links in the configured project. The
configured priority and issue type must exist in Jira. GitLab credentials need
Wiki read/create, issue create/assign, and user lookup access. Confluence support
targets Cloud v2; Jira and GitLab can use private/self-hosted installations.
Credentials are required only for selected providers. Disabled capabilities
return `503` and do not require placeholder credentials.

See [Provider configuration](docs/providers.md) for complete deployment examples
and instructions for adding a new adapter.

## Docker Compose

```bash
cp .env.example .env
# Edit .env first.
docker compose up --build -d
```

Compose persists state in a named volume. Keep one application replica: local
JSON storage is single-writer. See [architecture](docs/architecture.md).

## Helm

The chart contains only generic example values; replace all example hosts,
IDs, credentials, image coordinates, and recipients for your environment.

```bash
helm upgrade --install incidental ./helm/incidental \
  --namespace incidental --create-namespace \
  --set image.repository=ghcr.io/your-github-username/inci-dental \
  --set image.tag=0.1.0 \
  --set config.mattermostUrl=https://mattermost.example.com \
  --set config.mattermostTeamId=your-team-id \
  --set secret.mattermostApiToken=your-token \
  --set secret.incidentApiKey=your-long-random-key
```

For production, do not pass or commit secrets in Helm values. `existingSecret`
supplies the main API and Mattermost credentials. Provider-specific
`existingSecrets.confluence`, `existingSecrets.jira`, and `existingSecrets.gitlab`
can reference independently managed Secrets. Each must contain the corresponding
environment key (`CONFLUENCE_API_TOKEN`, `JIRA_API_TOKEN`, or `GITLAB_TOKEN`).
Select `config.reportProvider` and `config.actionProvider` and configure only
those providers. Set either to `none` to disable that capability. Persistence is
enabled by default; the deployment uses `Recreate` and one replica.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use fake ports and `httpx.MockTransport`; they do not need Mattermost,
Confluence, Jira, or any company credentials. Domain tests run with the Python
standard library alone.

## Project layout

```text
app/
  api/                    HTTP and bearer authentication
  application/incident/   Commands, queries, and reminder task
  application/reporting/  Report creation command
  application/actions/    Report-validated action creation command
  domain/incident/        Pure aggregate and abstract ports
  domain/reporting/       Report contract and value object
  domain/actions/         Provider-neutral action port
  infrastructure/incident/ Mattermost REST and JSON-state adapters
  infrastructure/reporting/ Confluence Cloud v2 adapter
  infrastructure/actions/ Jira Cloud / private Jira v2 adapter
  infrastructure/gitlab_adapter.py GitLab Wiki + issue adapter
  infrastructure/providers.py Configured provider registry
  HttpHandler/api.py      Composition root and app lifecycle
helm/incidental/          Generic single-replica Helm chart
tests/                    Domain, command, adapter, and API tests
```

## Operational limitations

- Exactly one process/replica may use the JSON state file.
- A failed initial-member lookup is logged; the channel and incident still
  succeed so responders can be invited manually.
- Incident channels are retained after resolution; archiving is left to your
  normal retention process.
- The static API key is suitable for trusted operators/automation. Put the API
  behind TLS and restrict network access; do not expose it directly to the
  public internet.
