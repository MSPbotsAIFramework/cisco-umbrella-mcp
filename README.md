# cisco-umbrella-mcp

Cisco Umbrella MCP Service — a stateless HTTP MCP server wrapping the [Cisco Umbrella REST API v2](https://developer.cisco.com/docs/cloud-security/) (classic Umbrella, not the newer Secure Access/SASE product), scoped to the 10 endpoints MSPbots currently uses: DNS/proxy/firewall/AMP-retrospective activity reports, roaming computers, app-discovery (applications/protocols/application categories), managed-provider customer list, and the provider console summary.

**Tech stack:** Python 3.12 + uv + FastMCP (Starlette/Uvicorn)

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## When would an agent use this

Cisco Umbrella protects a customer's network at the DNS/web layer — it blocks malicious domains, filters web content by category, and logs network activity. An agent should reach for this MCP for requests like:

- "Has this domain been queried or blocked on this customer's network recently?" → `cisco_umbrella_get_activity_dns`
- "What web categories/URLs are being filtered or proxied for this customer?" → `cisco_umbrella_get_activity_proxy`
- "Any firewall allows/blocks for this customer's network in the last day?" → `cisco_umbrella_get_activity_firewall`
- "Did a file that looked clean later get flagged as malware?" → `cisco_umbrella_get_activity_amp_retrospective`
- "List this customer's roaming laptops and their last sync/status" → `cisco_umbrella_list_roaming_computers`
- "List the customer orgs we manage under Cisco Umbrella" / "What's our Umbrella package usage across customers?" → `cisco_umbrella_list_customers`, `cisco_umbrella_get_providers_console`

**Caveat:** this credential set is a Managed Provider (MSSP) root-org key, not a per-customer credential, so the per-customer activity/device tools above may come back empty in practice — see [Known Gaps](#known-gaps) below for the verified details.

## Authentication method note

Cisco Umbrella's classic REST API supports the **OAuth2 client_credentials grant** — a pure server-to-server exchange, no user browser redirect. An admin creates an API Key + Key Secret pair in the Umbrella dashboard (Admin > API Keys), and this service exchanges that pair for a short-lived (1 hour) bearer token on every call (no refresh token, so no cross-request caching — same "re-login every call" pattern as `covedataprotection-mcp`/`webroot-mcp`/`logmein-mcp`).

```
POST https://api.umbrella.com/auth/v2/token
Authorization: Basic base64(apiKey:keySecret)
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
```

**Region note:** MSPbots' own integration config for Cisco Umbrella has a `dataCenter` field (`us`/`eu`). Verified directly against the raw OpenAPI spec embedded in Cisco's own developer docs for all 10 endpoints plus the auth/token endpoint: **every one of them lists exactly one host, `https://api.umbrella.com`** — there is no separate EU host for classic Umbrella. (Cisco's newer "Secure Access" product does have its own region concept, but that's a different product from what this service targets.) This service therefore ignores the `dataCenter` value entirely; it's not needed for any of these 10 endpoints.

## Quick Start

```powershell
# Install dependencies
cd D:\claude\project\cisco-umbrella-mcp
uv sync

# Run in stdio mode (for Claude Desktop)
$env:UMBRELLA_API_KEY="your_api_key"
$env:UMBRELLA_KEY_SECRET="your_key_secret"
uv run cisco-umbrella-mcp
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

| Variable | Default | Description |
|----------|---------|--------------|
| `UMBRELLA_API_KEY` | — | Cisco Umbrella API Key (Admin > API Keys) |
| `UMBRELLA_KEY_SECRET` | — | Cisco Umbrella Key Secret (shown once at creation time) |
| `AUTH_MODE` | `gateway` | `gateway` = credentials per-request via headers (SOP-compliant); `env` = shared credentials from env vars (local dev only) |
| `MCP_TRANSPORT` | `stdio` | `stdio` (Claude Desktop) or `http` (gateway) |
| `MCP_HTTP_PORT` | `8080` | HTTP server port |

## HEADER authentication parameters

In Gateway mode, every request must carry the following two HTTP headers:

| Header | Type | Required | Default | Allowed values | Description | Example |
|---|---|---|---|---|---|---|
| `X-Umbrella-Api-Key` | string | Yes | None | None | Cisco Umbrella API Key (generated on the Admin > API Keys page in the Umbrella console) | `AbCdEf1234567890` |
| `X-Umbrella-Key-Secret` | string | Yes | None | None | Cisco Umbrella Key Secret (shown only once at creation; used together with the API Key in the client_credentials flow to obtain a token) | `xyz9876543210abcdef` |

## Claude Desktop Setup

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cisco-umbrella": {
      "command": "uv",
      "args": ["run", "--directory", "D:/claude/project/cisco-umbrella-mcp", "cisco-umbrella-mcp"],
      "env": {
        "UMBRELLA_API_KEY": "your_api_key",
        "UMBRELLA_KEY_SECRET": "your_key_secret"
      }
    }
  }
}
```

## Transport Modes

### stdio (Claude Desktop / CLI)
```powershell
$env:UMBRELLA_API_KEY="your_api_key"
$env:UMBRELLA_KEY_SECRET="your_key_secret"
uv run cisco-umbrella-mcp
```

### HTTP — single-tenant
```powershell
$env:UMBRELLA_API_KEY="your_api_key"
$env:UMBRELLA_KEY_SECRET="your_key_secret"
$env:MCP_TRANSPORT="http"
$env:AUTH_MODE="env"
uv run cisco-umbrella-mcp
```

### HTTP — gateway / multi-tenant
```powershell
$env:MCP_TRANSPORT="http"
$env:AUTH_MODE="gateway"
uv run cisco-umbrella-mcp
# Each request must include: X-Umbrella-Api-Key and X-Umbrella-Key-Secret headers
```

## Available Tools (14)

| Tool | Description | API | Parameters |
|---|---|---|---|
| `cisco_umbrella_get_activity_dns` | DNS activity events | `GET /reports/v2/activity/dns` | `organization_id` (required), `from_`, `to` (required), `limit`, `offset`, `domains`, `categories`, `identityids`, `verdict`, `threats`, `timezone` |
| `cisco_umbrella_get_activity_proxy` | Proxy (SWG) activity events | `GET /reports/v2/activity/proxy` | `organization_id` (required), `from_`, `to` (required), `limit`, `offset`, `domains`, `urls`, `categories`, `identityids`, `verdict`, `threats`, `filename`, `timezone` |
| `cisco_umbrella_get_activity_firewall` | Firewall activity events | `GET /reports/v2/activity/firewall` | `organization_id` (required), `from_`, `to` (required), `limit`, `offset`, `identityids`, `ruleid`, `verdict`, `categories`, `timezone` |
| `cisco_umbrella_get_activity_amp_retrospective` | AMP retrospective activity events | `GET /reports/v2/activity/amp-retrospective` | `organization_id` (required), `from_`, `to` (required), `limit`, `offset`, `ampdisposition`, `sha256`, `timezone` |
| `cisco_umbrella_list_roaming_computers` | List roaming client endpoints | `GET /deployments/v2/roamingcomputers` | `organization_id` (required), `page`, `limit`, `name`, `status`, `swg_status`, `last_sync_before`, `last_sync_after` |
| `cisco_umbrella_list_applications` | List discovered cloud applications | `GET /reports/v2/appDiscovery/applications` | `organization_id` (required), `sources`, `identity`, `labels`, `controllable`, `categories`, `subcategory`, `limit`, `offset` |
| `cisco_umbrella_list_protocols` | List discovered network protocols | `GET /reports/v2/appDiscovery/protocols` | `organization_id` (required), `identity`, `limit`, `offset`, `sort`, `order` |
| `cisco_umbrella_list_application_categories` | List application categories | `GET /reports/v2/appDiscovery/applicationCategories` | `organization_id` (required), `limit`, `offset` |
| `cisco_umbrella_get_categories` | Category catalogue; `type` marks security vs content categories | `GET /reports/v2/categories` | `organization_id` (required) |
| `cisco_umbrella_get_summaries_by_category` | Per-category request counts for a time range | `GET /reports/v2/summaries-by-category` | `organization_id`, `from_`, `to` (required), `limit`, `offset`, `categories`, `domains`, `identityids`, `verdict`, `threats`, `threattypes`, `filternoisydomains` |
| `cisco_umbrella_list_networks` | List registered networks and their deployment state | `GET /deployments/v2/networks` | `organization_id` (required), `page`, `limit` |
| `cisco_umbrella_list_virtual_appliances` | List virtual appliances, their health and state | `GET /deployments/v2/virtualappliances` | `organization_id` (required), `page`, `limit` |
| `cisco_umbrella_list_customers` | List customer orgs under this Managed Provider account | `GET /admin/v2/managed/customers` | `page`, `limit` |
| `cisco_umbrella_get_providers_console` | Get provider console subscription/usage summary (single object, not a list) | `GET /reports/v2/providers/consoles` | none |

`from_`/`to` accept epoch milliseconds, ISO-8601, or a relative offset (e.g. `"-1days"`, `"-7days"`, `"now"`), per Umbrella's reporting API conventions. (`from_` has a trailing underscore because `from` is a Python reserved word — it's mapped to the literal `from` query parameter internally.)

`organization_id` is the managed customer's Umbrella organization ID (the `customerId` from `cisco_umbrella_list_customers`). It is sent as `X-Umbrella-OrgId` **on the token exchange**, so Umbrella mints a token whose `sub` claim is `org/<organization_id>/client/<key>`. It is **required** on every customer-scoped tool rather than optional. Omitting it would run the call at the provider (parent) organization's own scope, which answers `200` with either nothing or the parent's own traffic — indistinguishable downstream from "this customer had no activity in this period". Consumers of these tools state security findings to end clients, so a loud failure is safer than a quiet empty. Resolve an ID with `cisco_umbrella_list_customers`; the three provider-level tools (`list_customers`, `get_providers_console`, `test_connection`) deliberately do not take one.

## Known Gaps

Tested against two real Managed Provider (MSSP) accounts *before* per-customer scoping existed. Of the 10 tools that build had, only **2 were confirmed working with verified real data**; the other 8 were blocked or unverified (empty results don't prove correctness — they just mean no error was raised). The 4 tools added since have not been exercised live at all.

**Per-customer scoping, added 2026-09-18 — live-verified.** The empty results below were the expected consequence of running every call at the provider (parent) org's own scope, which carries no client traffic. `X-Umbrella-OrgId` fixes it, but **only on the token exchange**. Cisco's own docs give two placements and they disagree; tested against a live Managed Provider account with 62 managed customers:

| Placement | Result |
|---|---|
| Header on the business request (`GET /reports/v2/activity/dns`) | `200`, **`data: []`** — byte-identical to sending no scope at all |
| Header on `POST /auth/v2/token`, then call with the minted token | `200`, real rows, different per customer |

The failing placement fails *silently*, which is exactly the hazard this parameter exists to prevent — so this is pinned by `tests/test_tools.py::test_org_scope_is_applied_at_token_mint_not_on_the_business_request`. The scoped token's `sub` claim changes from `org/<parent>/client/<key>` to `org/<customer>/client/<key>`, and two customers return disjoint data. Because the token is minted per call and never cached, the scope cannot leak between tenants.

> **Breaking change, 2026-09-18.** `organization_id` became a required parameter on all 8 customer-scoped tools plus the 4 new ones. Calls that omit it now fail schema validation instead of silently returning parent-scope data. Agent sessions built against the previous signatures will break.

**✅ Confirmed working (real, non-empty, cross-validated data):**
- `cisco_umbrella_get_providers_console` — real subscription summary on both test accounts (`customerCount: 77` and `customerCount: 47` respectively).
- `cisco_umbrella_list_customers` — returned 77 real customer organizations (real company names) on account 1. Failed with `403 Access Forbidden` on account 2 — confirmed by decoding that account's token that it genuinely lacks the `admin.customers:read` scope (20 total scopes vs. 76 on account 1). Not a code bug; a real per-key permission difference.

**⚠️ Unverified — returned well-formed but empty results on both accounts, not proven correct:** `cisco_umbrella_get_activity_dns`, `_proxy`, `_firewall`, `_amp_retrospective`, `cisco_umbrella_list_roaming_computers`. Cross-checked the live OpenAPI parameter definitions for Activity DNS directly against Cisco's own docs (pulled the raw spec, not summarized) — `from`/`to`/`limit` are exactly as implemented, no missing/misnamed parameter. The likely explanation is that both test accounts are **Managed Provider root orgs**, which have no direct DNS/proxy/firewall/AMP traffic or roaming computers of their own — that data lives under each *managed customer* org individually. **Resolved by `organization_id` / `X-Umbrella-OrgId`** — the earlier conclusion here ("searched Cisco's docs for a scoping parameter/header, found none") was wrong. With a child-scoped token, `get_activity_dns` and `list_roaming_computers` return real per-customer data (verified on two customers). The app-discovery three remain blocked by entitlement, which is a separate problem.
- **`cisco_umbrella_list_applications`, `_protocols`, `_application_categories` (App Discovery) — confirmed blocked, not a code bug.** Reproduced identically on both test accounts and via direct curl with the same tokens (ruling out request-construction issues): `403 Access Forbidden` on account 1, `500`/`403` on account 2. Both tokens' scope lists included `reports.appdiscovery:read`, so this is most likely a package/entitlement restriction (App Discovery as a paid add-on not included in either account's "Umbrella for MSSPs" tier), not a permissions or parameter problem.
- `cisco_umbrella_get_providers_console` returns a single subscription-summary object, not a list — confirmed via both live tests. Despite the plural name in MSPbots' own configured API list ("Providers Consoles"), double-check this against whatever MSPbots' existing collector expects (array vs single object).
- The `Applications` app-discovery endpoint's optional parameter list may not be fully exhaustive (a couple of parameters near the end of that endpoint's schema were not fully captured during research) — the ones documented here (`sources`, `identity`, `labels`, `controllable`, `categories`, `subcategory`, `limit`, `offset`) are confirmed real; there may be one or two more not yet added.
- Scope is limited to the 14 operations MSPbots currently uses, not Umbrella's full API surface (which also includes Internal Domains, Sites, Network Tunnels, Policies, Tagging, the separate "Providers" API for per-customer actions, and the Key Admin API for managing API keys themselves). Whether Umbrella's `networks` and `sites` are the same objects under two names is an open question — the provider-side deployment response uses an identity type of `site`.

## API Reference

- [Cisco Umbrella API Authentication](https://developer.cisco.com/docs/cloud-security/umbrella-api-authentication/)
- [Cisco Cloud Security API Documentation (DevNet)](https://developer.cisco.com/docs/cloud-security/)

## Verified API behaviour (live, 2026-09-18)

Measured against a Managed Provider account with 62 managed customers. These
decide how a consumer must define its metrics, so they are recorded here
rather than left to be rediscovered.

- **`/reports/v2/categories` works at child-org scope and carries `type`.** 180
  categories, with six type values — `content` (153), `security` (13–15
  depending on org, the set includes per-customer entries), `system` (3),
  `aisupplychain` (3), `customer` (5), `application` (1). It is **not** a
  security/content binary; filter on `type == "security"` explicitly.
- **`summaries-by-category` omits categories with no traffic — it never
  returns a zero.** For one customer it returned 132 of 180 categories and
  *zero* rows with `requests == 0`. Of that org's 13 security categories only
  5 appeared; `Command and Control`, `Cryptomining` and
  `Drive-by Downloads/Exploits` were simply absent. **A consumer that needs to
  state "no command-and-control requests this month" must union the result
  against `/reports/v2/categories` and treat an absent row as zero** — reading
  the summary alone cannot distinguish "no traffic" from "no data".
- **Category counts do distinguish blocked from allowed.** The `summary`
  object carries `requests`, `requestsallowed`, `requestsblocked`, plus
  `applications`, `applicationsallowed`, `applicationsblocked`, `categories`,
  `domains`, `files`, `filetypes`, `identities`, `identitytypes`,
  `policycategories`, `policyrequests`.
- **The deployment endpoints return a bare JSON array** — no envelope, no
  `meta`, no total, no active count, and no count headers. Active counts must
  be derived by counting per-item state: `networks` has `status`
  (`OPEN`/`CLOSED`), `roamingcomputers` has `status` (`Open`/`Encrypted`/
  `Off`/`Disabled`) and `swgStatus`, `virtualappliances` has `health` and a
  `state` object.
- **`networks` and `sites` are different populations, not two names for one
  thing.** They are separate endpoints with disjoint fields; one test org had
  0 networks and 1 site, another had 2 networks and 1 site. A site looks like
  a container — it carries `internalNetworkCount` and `vaCount`.
- **⚠️ `summaries-by-category` must be called with `categories`, or the
  security rows are silently lost.** Unfiltered, one customer's month came
  back as 19,902 characters — over the 20,000-char response cap — so the
  wrapper truncated it to 53 of 132 rows and set `truncated: true`. The
  security categories sort last and **none of them survived**. Passing the 15
  security category IDs as `categories` returned 1,821 characters, 5 rows, no
  truncation. The working flow is two calls:

  ```
  cisco_umbrella_get_categories(organization_id)      -> keep ids where type == "security"
  cisco_umbrella_get_summaries_by_category(organization_id, from_, to,
                                           categories="<those ids, comma-separated>")
  ```

  Measured on one customer over 30 days: Malware 118 requests / 118 blocked,
  Newly Seen Domains 14/14, DNS Tunneling VPN 10/10, Dynamic DNS 8/0,
  Phishing 1/1.
- **⚠️ `offset` is unreliable on `summaries-by-category` — do not page with
  it.** With a 132-row result: `limit=10&offset=0` gave 10 rows,
  `limit=10&offset=5` gave 5, `limit=10&offset=10` gave **0**, and
  `limit=100&offset=50` gave 32. A consumer advancing `offset` by `limit`
  gets one page and then silence, producing a short census that looks
  complete. **Fetch the whole set in one call with a large `limit`** — the
  category population is bounded (~180), so `limit=200` covers it. `meta` is
  `{}` on every reporting response; there is no total to check against. The
  deployment endpoints page normally with `page`/`limit`.
