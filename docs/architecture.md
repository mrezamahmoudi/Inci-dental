# Architecture

Inci-dental is a focused incident-management service. It uses Hexagonal
Architecture: API handlers depend on application commands; application code
depends on pure domain objects and abstract ports; infrastructure implements
those ports. No dependency points out of the domain.

```text
HTTP request
    |
api/routers/incident.py -- authentication, validation, HTTP errors
    |
application/incident/commands.py -- StartIncident / EndIncident
    |
domain/incident/aggregate.py -- one active incident + group identity
    |
domain/incident/ports.py -- group and persistence contracts
    ^
infrastructure/incident/mattermost_adapter.py -- public Mattermost v4 REST API
infrastructure/incident/state_adapter.py -- atomic local JSON persistence

Reporting and actions use separate ports and commands:
api/routers/reporting.py
    -> application/reporting + application/actions
    -> domain/reporting + domain/actions
    <- infrastructure/reporting/confluence_adapter.py (Confluence Cloud v2)
    <- infrastructure/actions/jira_adapter.py (private Jira / Jira Cloud v2)
    <- infrastructure/gitlab_adapter.py (GitLab Wiki and issues)
    <- infrastructure/providers.py (runtime provider selection)
```

## Start sequence

1. Reject the request if another incident is active.
2. Create a private (configurable) Mattermost channel with a timestamped,
   title-derived name. Add explicitly configured initial members.
3. Save the active incident and complete channel identity to persistent storage.
4. Send the start announcement and responder service-review message to the new
   channel. A messaging failure is logged but does not hide the created group or
   encourage a duplicate incident.
5. Return the channel name and URL.

There is no dependency on an internal on-call service, a corporate directory,
or an existing "shift events" group. Membership is not periodically updated.

## End sequence

1. Send the end announcement to the active incident's channel.
2. Persist inactive state, then transition the aggregate to inactive.
3. If messaging fails, keep the incident active so the operator can retry.

The channel remains available for post-incident review. Inci-dental does not
rename, delete, archive, or rotate groups.

## Reports and actions

Reports are created explicitly through `POST /api/v1/incident-reports`, separate
from the incident state machine. The selected Confluence or GitLab adapter renders
the built-in summary, impact, root-cause, timeline, resolution, and follow-up
template. Confluence storage-format user text is escaped; GitLab uses Markdown.

`POST /api/v1/actions` accepts description, assignee, priority, report ID, and an
optional title. The application command resolves the report through the selected
report provider to a `ReportReference(provider, id, url)`, then the selected Jira
or GitLab adapter creates an assigned, prioritized action linked to that URL.
The caller selects the on-call assignee; no internal on-call lookup is performed.
A Jira issue can remain created if its subsequent remote-link request fails; the
`502` response should be reconciled by an operator.

`REPORT_PROVIDER`, `ACTION_PROVIDER`, and `CHAT_PROVIDER` select adapters at the
composition root. Reporting/action providers default to `none` and require no
credentials while disabled. The provider registry translates unknown or disabled
selections into `503`; it does not invent fallback providers or hosts. Jira
Cloud is opt-in (`JIRA_CLOUD=true`), with private Jira the default. GitLab works
against SaaS or private installations. See [providers.md](providers.md).

## Persistence and concurrency

The JSON file is atomically replaced on each state transition. The aggregate is
restored at startup. This is deliberately single-writer storage: **run exactly
one replica**. A multi-replica deployment requires a transactional shared store
and a new `IncidentStatePort` adapter.

State is saved immediately after group creation, before notifications. This
preserves the group reference after a restart or a temporary messaging outage.
The in-memory aggregate enforces duplicate starts within the single process.

## Reminders

One async task waits for the configured interval and posts a reminder to the
active incident's own channel. It is cancelled on graceful shutdown. There are
no simulation, shedding, migration, shift-delivery, or group-update tasks.

## Security and observability

- Mutating endpoints require a static bearer key. `X-Actor` supplies an optional
  audit label; it is not proof of a user's identity.
- Mattermost uses a personal access token. It is sent only in the HTTPS
  Authorization header and is never logged.
- Mattermost permissions required: create channels in the configured team,
  read users by email, add channel members, and create posts. Private-channel
  permissions must match the configured channel type.
- Confluence Cloud uses email/token basic auth and needs page read/create access.
  Jira Cloud uses email/token basic auth; Data Center uses bearer personal tokens.
  Jira needs issue create/assign and remote-link permissions. GitLab uses a
  PRIVATE-TOKEN and needs Wiki, issue, and user-read permissions. All credentials
  are injected as secrets and excluded from error messages and logs.
- `/healthz` is unauthenticated and exposes only `{"status":"ok"}`.
- `/metrics` is unauthenticated and should be exposed only to your monitoring
  network. It contains actor labels, not tokens or incident titles.
- Logs identify actions and channels, but not message contents or credentials.

## Configuration

All external URLs, team IDs, member lists, credentials, and timing values are
runtime configuration. No company endpoint or Helm environment is embedded in
the service. See the README for the complete environment-variable reference.
