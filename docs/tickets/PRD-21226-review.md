# PRD-21226 · Code review

## Round 1 · 2026-10-30 · reviewed dev/PRD-21226 @ b8f9ff7 (base c59fd0d)

Verdict: changes requested

### Findings

1. [must-fix] `docs/tickets/PRD-21226.md` "Option analysis" / `README.md:188` — This change raises the server's tool count from 15 (14 existing + `cisco_umbrella_test_connection`) to 23, past the SOP's documented reference budget of ≤20 tools per service (`vendor-mcp-development-sop.md` §2.1: "单个服务工具数 应当 ≤ 20；超出请在交付说明里逐条说明为什么不能合并"). The design's "Option analysis" section only argues against one alternative (a single mega-tool with a `resource` enum, or a generic passthrough tool) — it does not address whether any of the 8 new tools could be merged with each other. Two candidates stand out and are not discussed: (a) the three `investigate.py` tools (`cisco_umbrella_get_domain_categorization`, `_get_domain_risk_score`, `_get_domain_whois`) are all single-domain-keyed GETs with no other required parameters and no `organization_id` scoping — a plausible case for one `cisco_umbrella_get_domain_intel(domain, aspect: Literal["categorization","risk_score","whois"])`-shaped tool, or at least an explicit note on why three separate tools read better for an agent; (b) `cisco_umbrella_get_destination_list_destinations` could be an optional `destination_list_id` branch of `cisco_umbrella_list_destination_lists` rather than a second tool. Per SOP §14 Checklist ("面向 Agent 设计"), going over budget without this explanation is a checklist item left unchecked, and `references/mcp-track.md` §4.3 lists "SOP §14 Checklist" as one of the must-fix review criteria for MCP tickets. Fix: either consolidate the clearly-mergeable tools, or add a short paragraph to `docs/tickets/PRD-21226.md`'s Option analysis (and a matching note in README Known Gaps) explaining why each of the 8 new tools needs to stay separate. Everything else in the design/self-test evidence is otherwise sound, so a documented justification is an acceptable resolution if consolidation turns out to hurt clarity more than it helps.

### Independently verified (no discrepancy from the Self-test section)

- `uv sync && uv run pytest -q` on `b8f9ff7`: 26 passed (matches the Self-test table).
- `uv run ruff check` on the 5 touched/new files: clean (matches).
- In-process `mcp.list_tools()` (`AUTH_MODE=env`): 23 tools, names match the Self-test table exactly.
- Chinese-character scan (`src tests README.md docs`): no matches.
- README "MSPbots Connector" section (lines 7–30): byte-identical to `reference/readme-connector-section.md` lines 1–24 (section is unmodified by this diff).
- `api_client.py`, `config.py`, `tools/_common.py`, `_json.py` confirmed unmodified — all 8 new tools reuse `UmbrellaClient.get()`, `NO_TOKEN`, `dump_json_capped`/`error_envelope` verbatim; credentials still flow only through `client_factory()` / request-scoped headers, no new logging or persistence of `api_key`/`key_secret`.
- `limit` default 100 / hard cap 200 on the two paginated policies tools matches the repo-wide existing convention in `reports.py` (not a new deviation introduced by this change).
- New path-segment interpolation (`destination_list_id`, `domain`) is `urllib.parse.quote()`-escaped — a safe pattern with no prior precedent to copy from in this repo, no issue found.

### Fixes (round 1, dev)

Chose consolidation over a written justification — doing both landed the tool count exactly at the SOP's ≤20 budget, which is a stronger signal than a prose exemption would have been.

1. **`cisco_umbrella_get_domain_categorization` / `_get_domain_risk_score` / `_get_domain_whois` → `cisco_umbrella_get_domain_intel(domain, aspect)`** (`src/cisco_umbrella_mcp/tools/investigate.py`). `aspect: Literal["categorization", "risk_score", "whois"]` selects the upstream path; `showlabels` is kept but only applied (as the `showLabels` query param) when `aspect="categorization"`, otherwise `params=None`. All three were single-domain-keyed GETs with no other required parameter and no `organization_id` scoping — the review's own framing ("look up what Cisco knows about this domain") read as one capability, not three. This is the finding's candidate (a).
2. **`cisco_umbrella_get_destination_list_destinations` → optional `destination_list_id` on `cisco_umbrella_list_destination_lists`** (`src/cisco_umbrella_mcp/tools/policies.py`). Omitted: `GET /policies/v2/destinationlists` (list of lists, unchanged behavior). Given: `GET /policies/v2/destinationlists/{id}/destinations` (one list's contents). This is candidate (b); AC2's own text already anticipated this exact shape ("gets back that customer's destination lists (or, given a destination_list_id, the destinations inside one list)"), so no design deviation here, just an implementation choice the design had already left room for.
3. **`server.py`** — updated the `instructions=` string's tool names to the consolidated set (now 1339/1500 chars).
4. **`tests/test_tools.py`** — `EXPECTED_TOOLS`/`NO_ORG_SCOPE_TOOLS` updated to the 20-tool set; the 6 tests touching the retired tool names now call the consolidated tools with the matching `aspect`/`destination_list_id` argument; added `test_list_destination_lists_with_id_returns_one_lists_destinations` to cover the new optional-param branch (no prior test exercised that path, since the old two-tool shape made it a second tool's job).
5. **`docs/tickets/PRD-21226.ac.json`** — TC6/TC7/TC8/TC9 evidence refreshed to name the consolidated tool and re-run results; TC3's evidence notes it now also covers the "`destination_list_id` omitted" branch explicitly; added `TC-DEV1` (`source: dev`) exercising the `destination_list_id` branch directly, tied to AC2. No `text`/`ac`/`type` field was changed on any existing case — only `evidence` (dev-owned) was refreshed, and TC-DEV1 is additive dev-perspective coverage per `legs/dev.md` S1 "追加用例的效力", not a change to a design-owned case.
6. **`README.md`** — tool count 22 → 20, tool table rows merged to match, "When would an agent use this" examples updated, two `Known Gaps` sentences that named the retired tool/test names updated to the consolidated ones. The "MSPbots Connector" section (lines 7–30) was not touched.
7. **`docs/tickets/PRD-21226.md` (frozen)** — left untouched per `legs/dev.md` S1 "Review rework": this Fixes section is the record of what changed and why.

**Re-run after the fix**, commit `6382805` on `dev/PRD-21226` (still `origin/main@c59fd0d` — `main` had not moved since round 1, no re-sync needed):

- `uv sync && uv run pytest -q` → 27 passed (19 existing + 8 touching this change — the 7 from round 1 plus the new `TC-DEV1` test), 0 failed.
- `uv run ruff check` on the 4 touched files (`investigate.py`, `policies.py`, `server.py`, `tests/test_tools.py`) → clean.
- In-process `mcp.list_tools()` (`AUTH_MODE=env`) → **20 tools** (was 23), names as listed above; every tool's `required` set verified against its intended scoping (`cisco_umbrella_get_domain_intel` requires `domain`+`aspect`, no `organization_id`; `cisco_umbrella_list_destination_lists` requires only `organization_id`, `destination_list_id` optional).
- HTTP + gateway transport smoke (`uv run cisco-umbrella-mcp`, `MCP_TRANSPORT=http AUTH_MODE=gateway`, port 8123, driven via `mcp.client.streamable_http`): `GET /health` → `200 {"status":"ok"}`; `initialize` with no `X-Umbrella-*` headers → `401`; with placeholder headers → `tools/list` returns the same 20 tools; `tools/call cisco_umbrella_get_domain_intel(aspect="risk_score")` with placeholder (fake) credentials → real upstream `401` from `api.umbrella.com`, mapped to `{"error":{"code":"unauthorized","message":"Unauthorized","retryable":false}}`, no stack trace.
- Chinese-character scan (`src tests README.md docs`) → no matches introduced by this fix (the only hit remains this review doc's own quote of the SOP's Chinese text in Round 1 Finding 1 above, pre-existing from the review commit itself, not part of the diff this Fixes section covers).
- README "MSPbots Connector" section (lines 7–30): still byte-identical to `reference/readme-connector-section.md` lines 1–24 — unmodified by this fix.
- `gitleaks` not installed in this sandbox; not run (same as round 1).

## Round 2 · 2026-10-30 · reviewed dev/PRD-21226 @ b1e2de8 (base c59fd0d)

Status: frozen @ b1e2de8

Verdict: approved

### Findings

None. Round 1's single must-fix is resolved: the 3 `investigate.py` tools were consolidated into `cisco_umbrella_get_domain_intel(domain, aspect)` and `cisco_umbrella_get_destination_list_destinations` was folded into `cisco_umbrella_list_destination_lists(destination_list_id optional)`, bringing the tool count from 23 to exactly 20 — the SOP §2.1 budget — rather than relying on a written exemption. Both consolidations match AC2/AC4/AC5's own wording and change no response shape or scoping behavior; only the surface (tool name/params) changed.

### Independently verified (no discrepancy from the Fixes section or Self-test)

- Diff reviewed: `b8f9ff7...b1e2de8` (7 files: `README.md`, `PRD-21226-review.md`, `PRD-21226.ac.json`, `server.py`, `investigate.py`, `policies.py`, `tests/test_tools.py`).
- `uv sync && uv run pytest -q` on `b1e2de8`: 27 passed, 0 failed (matches the Fixes section).
- `uv run ruff check` on the 4 touched source files: clean (matches).
- In-process `mcp.list_tools()` (`AUTH_MODE=env`): **20 tools**, names match the README table and `EXPECTED_TOOLS`/`NO_ORG_SCOPE_TOOLS` in `tests/test_tools.py` exactly; `cisco_umbrella_get_domain_intel` requires `domain`+`aspect` only (no `organization_id`), `cisco_umbrella_list_destination_lists` requires only `organization_id` (`destination_list_id` optional) — matches the Fixes section.
- HTTP+gateway smoke, run independently on port 8080 (`MCP_TRANSPORT=http AUTH_MODE=gateway`): `GET /health` → `200`; `POST /mcp initialize` with no `X-Umbrella-*` headers → `401`. Matches the Fixes section's claim.
- Chinese-character scan (`src tests README.md docs`): the only hit is this review doc's own Round 1 quote of the SOP's Chinese text — pre-existing from the review commit, not introduced by this fix. No Chinese in shipped code, tests, or README.
- README "MSPbots Connector" section: still byte-identical to `reference/readme-connector-section.md`.
- `src/cisco_umbrella_mcp/api_client.py`, `config.py`, `tools/_common.py`, `_json.py` confirmed unmodified in this diff range — credential handling (Header-only, request-scoped) and the error-envelope/JSON-capping helpers are untouched.
- `docs/tickets/PRD-21226.ac.json`: only `evidence` fields changed on TC1/TC3/TC6/TC7/TC8/TC9 (re-run notes); no `text`/`ac`/`type` field touched on any existing case. `TC-DEV1` is correctly marked `"source": "dev"` and is additive coverage for the new optional-param branch, not a substitute for a design-owned case.
- Noted in passing, not a finding: at `b8f9ff7` (pre-fix), the actual in-process tool count was 23 but the README header read "Available Tools (22)" (off-by-one, pre-existing doc drift, not introduced by round 1). The consolidation lands on the correct count (20) and the header now matches exactly — no action needed since the current state is correct.
- SOP §14 Checklist re-checked against `b1e2de8`: tool count ≤ 20 now satisfied; all other items (Header-only credentials, request isolation, structured errors, `readOnlyHint` annotations, `limit`/`offset` pagination, README Header table and Connector section, English-only content) were already clean in round 1 and unaffected by this fix.

No must-fix, no suggestions. Approved for merge into `main`, INT publish, and connector wiki.
