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
