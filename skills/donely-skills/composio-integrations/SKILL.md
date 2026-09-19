---
name: composio-integrations
description: "Connect, authenticate, or act on third-party apps — HubSpot, ClickUp, Gmail, Salesforce, Google Calendar, and 500+ others — via the built-in Composio tools. Use whenever the user asks to connect / integrate / automate / read / write an external app, or asks 'can I connect <app>?', AND no dedicated skill for that specific app exists. If a purpose-built skill for the app is present (e.g. a slack / linear / notion / github skill), prefer that instead. When Composio is the path, return an OAuth connect link — never offer API tokens, MCP servers, or webhooks as alternatives."
version: 1.2.0
metadata:
  hermes:
    tags: [integrations, composio, oauth, apps]
    requires_tools: [mcp_composio_COMPOSIO_SEARCH_TOOLS]
---

# Composio Integrations (1,000+ apps, already connected)

You have a **built-in Composio Tool Router** exposed as NATIVE tools. It is the single,
official way you connect to and act on external apps. No API keys from the user, no new
MCP server, no webhooks — Composio already handles all of that.

## First: does a dedicated skill already cover this app?
Composio is the **fallback** for the 500+ apps that have no purpose-built skill. If your skills
list already has a dedicated skill for the requested app (e.g. `slack-automation`, `linear`,
`notion`, a `github-*` skill), **prefer that** — it's purpose-built and uses the right auth for
that app. Reach for Composio only when no dedicated skill covers the app. Either way, pick ONE
path — never present the user a menu of options.

## CRITICAL — how to answer "can I connect <App>?" when Composio is the path (HubSpot, ClickUp, Gmail, …)
For an app with no dedicated skill, Composio is the **only** path you offer. Do **NOT** list
options or alternatives. Do **NOT** mention "the REST API", "an API token", "an MCP server", or
"webhooks". Respond by **immediately connecting it**:

1. Say yes, briefly, and that you're setting it up now.
2. Call `mcp_composio_COMPOSIO_MANAGE_CONNECTIONS` for that app to start OAuth — it returns a
   connect link.
3. Give the user that link as a **clickable markdown link** ("Connect ClickUp") and ask them
   to authorize. Mention it opens the app's auth page and activates automatically.
4. After they authorize, use `mcp_composio_COMPOSIO_SEARCH_TOOLS` →
   `mcp_composio_COMPOSIO_GET_TOOL_SCHEMAS` → `mcp_composio_COMPOSIO_MULTI_EXECUTE_TOOL` to do
   the actual work.

A good answer looks like: *"Yes — click this link to connect ClickUp: **[Connect ClickUp](…)**.
Once you authorize, I'll be able to read/create tasks, update statuses, manage lists, and more."*
A BAD answer lists "1. ClickUp API  2. MCP server  3. Composio" — never do that.

## Your native Composio tools (call directly, not via mcporter)
- `mcp_composio_COMPOSIO_SEARCH_TOOLS` — find tools for an app/task.
- `mcp_composio_COMPOSIO_MANAGE_CONNECTIONS` — connect a new app via OAuth; returns the link.
- `mcp_composio_COMPOSIO_GET_TOOL_SCHEMAS` — fetch a tool's input schema before executing.
- `mcp_composio_COMPOSIO_MULTI_EXECUTE_TOOL` — execute one or more app tools (parallel ok).
- `mcp_composio_COMPOSIO_REMOTE_BASH_TOOL` / `mcp_composio_COMPOSIO_REMOTE_WORKBENCH` — remote bash / bulk ops.

## Notes
- Integrations are free for the user (no per-action credit charge).
- If a connection has expired, re-run MANAGE_CONNECTIONS to re-auth.
- Don't surface the word "Composio" or internal URLs to the user unless debugging — to them
  it's simply "connecting your apps".
