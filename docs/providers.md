# Provider configuration

External products are selected at deployment time. The domain and HTTP request
contracts describe incident capabilities, not a particular vendor. Mattermost,
Confluence, Jira, and GitLab are implementations behind ports; no internal SDK
or fixed company host is required.

## Selectors

| Variable | Values | Default |
|---|---|---|
| `CHAT_PROVIDER` | `mattermost` | `mattermost` |
| `REPORT_PROVIDER` | `confluence`, `gitlab`, `none` | `none` |
| `ACTION_PROVIDER` | `jira`, `gitlab`, `none` | `none` |

`none` disables a capability. Its endpoint returns `503`; credentials for that
capability are not required. Only selected providers are instantiated and only
their required settings are validated.

An action request can specify `related_report_provider` to verify a report in a
provider different from the configured default. Report responses include
`provider`, `report_id`, and `url`; actions use a provider-neutral reference,
so Jira can link to either Confluence or GitLab reports.

## Private/self-hosted Jira

```dotenv
REPORT_PROVIDER=confluence
ACTION_PROVIDER=jira
JIRA_URL=https://jira.internal.example
JIRA_CLOUD=false
JIRA_EMAIL=
JIRA_API_TOKEN=your-personal-access-token
JIRA_PROJECT_KEY=INC
JIRA_ISSUE_TYPE=Task
```

Use a Jira **username** as `assignee`. Jira Cloud is explicitly opt-in with
`JIRA_CLOUD=true` and `JIRA_EMAIL`; its assignee is an **accountId**. Priority
must match the target instance, for example `High`.

## GitLab (SaaS or private)

```dotenv
REPORT_PROVIDER=gitlab
ACTION_PROVIDER=gitlab
GITLAB_URL=https://gitlab.internal.example
GITLAB_TOKEN=your-access-token
GITLAB_PROJECT_ID=operations/sre
```

Reports are project Wiki pages. Actions are assigned project issues, linked to
the report in the description. Priority becomes `priority::<value>` alongside
the `incident-action` label; configure matching GitLab labels if desired.
`assignee` is a GitLab username. The token needs API access and permission to
read Wiki pages, create Wiki pages/issues, and resolve the assignee.

A numeric project ID or `namespace/project` path works. Do not pre-encode the
slash in an environment value; the adapter URL-encodes the path.

## Confluence Cloud reports

```dotenv
REPORT_PROVIDER=confluence
CONFLUENCE_URL=https://your-site.atlassian.net
CONFLUENCE_EMAIL=your-account@example.com
CONFLUENCE_API_TOKEN=your-api-token
CONFLUENCE_SPACE_ID=123456
CONFLUENCE_PARENT_PAGE_ID=
```

This adapter targets Confluence Cloud v2 and uses a numeric space ID. Confluence
Data Center would need a separate adapter implementing `IncidentReportPort`.

## Mattermost chat

Mattermost is currently the built-in incident-group implementation. Additional
chat products should be added by implementing `IncidentGroupPort`, then selected
in the composition root—not by adding provider logic to application commands.

## Adding another provider

1. Implement `IncidentReportPort`, `ActionItemPort`, or `IncidentGroupPort`.
2. Translate the generic report/action data to that provider's public API.
3. Resolve reports to `ReportReference(provider, report_id, url)`.
4. Register the adapter only when selected in `HttpHandler/api.py`.
5. Add generic environment/Helm examples and mocked adapter/provider tests.

Do not import provider SDKs or clients into `domain/` or `application/`. Do not
require credentials for unselected integrations. Never log tokens or upstream
response bodies.
