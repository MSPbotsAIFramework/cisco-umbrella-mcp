"""tools/list snapshot + error-envelope mapping tests.

No network calls: tool enumeration goes through FastMCP's in-process
list_tools(), and the error-code mapping is tested directly against
UmbrellaError, independent of any real HTTP request.
"""

import pytest

from cisco_umbrella_mcp.api_client import UmbrellaError
from cisco_umbrella_mcp.config import Settings
from cisco_umbrella_mcp.server import create_mcp_server

# Every customer-scoped tool requires organization_id — it becomes the
# X-Umbrella-OrgId header. The three provider-level tools below do not take
# it: they are how a caller discovers an organization_id in the first place.
EXPECTED_TOOLS = {
    "cisco_umbrella_test_connection": set(),
    "cisco_umbrella_get_activity_dns": {"organization_id", "from_", "to"},
    "cisco_umbrella_get_activity_proxy": {"organization_id", "from_", "to"},
    "cisco_umbrella_get_activity_firewall": {"organization_id", "from_", "to"},
    "cisco_umbrella_get_activity_amp_retrospective": {"organization_id", "from_", "to"},
    "cisco_umbrella_get_summaries_by_category": {"organization_id", "from_", "to"},
    "cisco_umbrella_get_categories": {"organization_id"},
    "cisco_umbrella_list_roaming_computers": {"organization_id"},
    "cisco_umbrella_list_networks": {"organization_id"},
    "cisco_umbrella_list_virtual_appliances": {"organization_id"},
    "cisco_umbrella_list_applications": {"organization_id"},
    "cisco_umbrella_list_protocols": {"organization_id"},
    "cisco_umbrella_list_application_categories": {"organization_id"},
    # provider-level: no customer scope
    "cisco_umbrella_list_customers": set(),
    "cisco_umbrella_get_providers_console": set(),
    # PRD-21226: admin — provider-level, same reasoning as list_customers
    "cisco_umbrella_list_api_keys": set(),
    # PRD-21226: policies — customer-scoped, same pattern as reports.py
    "cisco_umbrella_list_destination_lists": {"organization_id"},
    "cisco_umbrella_get_destination_list_destinations": {"organization_id", "destination_list_id"},
    "cisco_umbrella_list_application_lists": {"organization_id"},
    "cisco_umbrella_get_application_usage": {"organization_id"},
    # PRD-21226: investigate — global threat intel, no customer scope
    "cisco_umbrella_get_domain_categorization": {"domain"},
    "cisco_umbrella_get_domain_risk_score": {"domain"},
    "cisco_umbrella_get_domain_whois": {"domain"},
}

# Tools that must NOT gain organization_id, for two different reasons:
# a provider credential is the whole point of the admin/provider-level
# ones (test_connection, list_customers, get_providers_console,
# list_api_keys); the investigate ones are a global Cisco dataset keyed
# by domain, not per-managed-customer data (PRD-21226 design doc OQ3).
NO_ORG_SCOPE_TOOLS = {
    "cisco_umbrella_test_connection",
    "cisco_umbrella_list_customers",
    "cisco_umbrella_get_providers_console",
    "cisco_umbrella_list_api_keys",
    "cisco_umbrella_get_domain_categorization",
    "cisco_umbrella_get_domain_risk_score",
    "cisco_umbrella_get_domain_whois",
}


@pytest.mark.asyncio
async def test_tools_list_snapshot():
    mcp = create_mcp_server(Settings())
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == set(EXPECTED_TOOLS), f"unexpected tool set: {names}"

    by_name = {t.name: t for t in tools}
    for name, expected_required in EXPECTED_TOOLS.items():
        tool = by_name[name]
        required = set(tool.inputSchema.get("required", []))
        assert required == expected_required, f"{name}: required={required}"
        assert tool.annotations is not None and tool.annotations.readOnlyHint is True
        assert len(tool.description or "") <= 500, f"{name}: description too long"
        first_line = (tool.description or "").strip().splitlines()[0]
        assert len(first_line) <= 100, f"{name}: first line too long: {first_line!r}"

        # Scope must be explicit, never inferred from the token's own org.
        properties = tool.inputSchema.get("properties", {})
        if name in NO_ORG_SCOPE_TOOLS:
            assert "organization_id" not in properties, f"{name}: should not be customer-scoped"
        else:
            assert "organization_id" in required, f"{name}: organization_id must be required"


@pytest.mark.asyncio
async def test_service_instructions_present_and_bounded():
    mcp = create_mcp_server(Settings())
    assert mcp.instructions
    assert len(mcp.instructions) <= 1500


@pytest.mark.parametrize(
    "status_code,expected_code,expected_retryable",
    [
        (0, "upstream_error", True),
        (400, "invalid_argument", False),
        (401, "unauthorized", False),
        (403, "unauthorized", False),
        (404, "not_found", False),
        (422, "invalid_argument", False),
        (429, "rate_limited", True),
        (500, "upstream_error", True),
        (503, "upstream_error", True),
    ],
)
def test_error_envelope_mapping(status_code, expected_code, expected_retryable):
    import json

    err = UmbrellaError(status_code, "boom")
    envelope = json.loads(err.to_envelope())
    assert envelope["error"]["code"] == expected_code
    assert envelope["error"]["retryable"] is expected_retryable
    assert envelope["error"]["message"] == "boom"


@pytest.mark.asyncio
async def test_customer_scope_reaches_the_client_not_the_query_string():
    """organization_id is handed to the client as scope, never as a query
    parameter — Umbrella has no such query parameter.
    """
    from mcp.server.fastmcp import FastMCP

    from cisco_umbrella_mcp.tools import reports

    captured = {}

    class _StubClient:
        async def get(self, path, params=None, organization_id=None):
            captured["path"] = path
            captured["params"] = params
            captured["organization_id"] = organization_id
            return {"data": []}

    mcp = FastMCP(name="test")
    reports.register(mcp, lambda: _StubClient())
    await mcp.call_tool(
        "cisco_umbrella_get_summaries_by_category",
        {"organization_id": "1234567", "from_": "-30days", "to": "now"},
    )
    assert captured["path"] == "/reports/v2/summaries-by-category"
    assert captured["organization_id"] == "1234567"
    assert "organization_id" not in captured["params"]


@pytest.mark.asyncio
async def test_org_scope_is_applied_at_token_mint_not_on_the_business_request():
    """X-Umbrella-OrgId only works on POST /auth/v2/token.

    Verified live 2026-09-18 against a Managed Provider account: the same
    header on the business request returns 200 with an empty data array,
    indistinguishable from "this customer had no activity". Umbrella
    instead mints a token whose sub claim is org/<id>/client/<key>. If this
    test is ever loosened, that silent-empty failure mode comes back.
    """
    import httpx

    from cisco_umbrella_mcp import api_client

    captured = {}

    async def fake_request_with_retry(method, url, *, headers, params=None, data=None):
        captured.setdefault("calls", []).append((url, dict(headers)))
        if url == api_client.TOKEN_URL:
            return httpx.Response(200, json={"access_token": "scoped-token"})
        return httpx.Response(200, json={"data": []})

    original = api_client._request_with_retry
    api_client._request_with_retry = fake_request_with_retry
    try:
        client = api_client.UmbrellaClient("key", "secret")
        await client.get("/reports/v2/categories", organization_id="1234567")
    finally:
        api_client._request_with_retry = original

    (token_url, token_headers), (business_url, business_headers) = captured["calls"]
    assert token_url == api_client.TOKEN_URL
    assert token_headers["X-Umbrella-OrgId"] == "1234567"
    assert "X-Umbrella-OrgId" not in business_headers
    assert business_headers["Authorization"] == "Bearer scoped-token"


@pytest.mark.asyncio
async def test_provider_level_calls_mint_an_unscoped_token():
    """Without organization_id the token stays at provider scope — that is
    what cisco_umbrella_list_customers needs to enumerate customers.
    """
    import httpx

    from cisco_umbrella_mcp import api_client

    captured = {}

    async def fake_request_with_retry(method, url, *, headers, params=None, data=None):
        captured.setdefault("calls", []).append((url, dict(headers)))
        if url == api_client.TOKEN_URL:
            return httpx.Response(200, json={"access_token": "parent-token"})
        return httpx.Response(200, json={"data": []})

    original = api_client._request_with_retry
    api_client._request_with_retry = fake_request_with_retry
    try:
        await api_client.UmbrellaClient("key", "secret").get("/admin/v2/managed/customers")
    finally:
        api_client._request_with_retry = original

    _, token_headers = captured["calls"][0]
    assert "X-Umbrella-OrgId" not in token_headers


# ── PRD-21226: admin / policies / investigate tools ─────────────────────────


@pytest.mark.asyncio
async def test_list_api_keys_returns_metadata_without_secret():
    """TC1 (AC1): cisco_umbrella_list_api_keys returns key metadata, never a secret."""
    import json

    from mcp.server.fastmcp import FastMCP

    from cisco_umbrella_mcp.tools import admin

    class _StubClient:
        async def get(self, path, params=None, organization_id=None):
            assert path == "/admin/v2/apiKeys"
            assert organization_id is None
            return [
                {"id": "k1", "label": "prod", "scope": ["reports:read"], "status": "active"},
                {
                    "id": "k2",
                    "label": "backup",
                    "scope": ["admin.apikeys:read"],
                    "status": "active",
                },
            ]

    mcp = FastMCP(name="test")
    admin.register(mcp, lambda: _StubClient())
    blocks = await mcp.call_tool("cisco_umbrella_list_api_keys", {})
    keys = json.loads(blocks[1]["result"])
    assert len(keys) == 2
    for key in keys:
        assert "secret" not in key and "keySecret" not in key
        assert {"id", "label", "scope", "status"} <= set(key)


@pytest.mark.asyncio
async def test_list_destination_lists_is_scoped_by_organization_id():
    """TC3 (AC2): organization_id reaches the client as scope, matching reports.py."""
    from mcp.server.fastmcp import FastMCP

    from cisco_umbrella_mcp.tools import policies

    captured = {}

    class _StubClient:
        async def get(self, path, params=None, organization_id=None):
            captured["path"] = path
            captured["params"] = params
            captured["organization_id"] = organization_id
            return [
                {
                    "id": "dl1",
                    "name": "Blocklist",
                    "access": "block",
                    "isGlobal": False,
                    "destinationCount": 3,
                }
            ]

    mcp = FastMCP(name="test")
    policies.register(mcp, lambda: _StubClient())
    await mcp.call_tool("cisco_umbrella_list_destination_lists", {"organization_id": "1234567"})
    assert captured["path"] == "/policies/v2/destinationlists"
    assert captured["organization_id"] == "1234567"
    assert "organization_id" not in captured["params"]


@pytest.mark.asyncio
async def test_application_lists_and_usage_round_trip():
    """TC5 (AC3): application lists and application usage round-trip through client.get."""
    import json

    from mcp.server.fastmcp import FastMCP

    from cisco_umbrella_mcp.tools import policies

    responses = {
        "/policies/v2/applicationLists": [
            {"id": "al1", "name": "Approved Apps", "isDefault": True, "applicationCount": 5}
        ],
        "/policies/v2/applications/usage": [
            {"applicationId": "a1", "name": "Dropbox", "category": "File Sharing", "usageCount": 42}
        ],
    }

    class _StubClient:
        async def get(self, path, params=None, organization_id=None):
            assert organization_id == "1234567"
            return responses[path]

    mcp = FastMCP(name="test")
    policies.register(mcp, lambda: _StubClient())

    org_args = {"organization_id": "1234567"}
    lists_blocks = await mcp.call_tool("cisco_umbrella_list_application_lists", org_args)
    assert json.loads(lists_blocks[1]["result"]) == responses["/policies/v2/applicationLists"]

    usage_blocks = await mcp.call_tool("cisco_umbrella_get_application_usage", org_args)
    assert json.loads(usage_blocks[1]["result"]) == responses["/policies/v2/applications/usage"]


@pytest.mark.asyncio
async def test_domain_categorization_returns_security_categories():
    """TC6 (AC4): domain categorization returns security/content categories, no organization_id."""
    import json

    from mcp.server.fastmcp import FastMCP

    from cisco_umbrella_mcp.tools import investigate

    captured = {}

    class _StubClient:
        async def get(self, path, params=None, organization_id=None):
            captured["path"] = path
            captured["organization_id"] = organization_id
            return {
                "example.com": {
                    "status": 1,
                    "content_categories": ["Business"],
                    "security_categories": ["Malware"],
                }
            }

    mcp = FastMCP(name="test")
    investigate.register(mcp, lambda: _StubClient())
    blocks = await mcp.call_tool(
        "cisco_umbrella_get_domain_categorization", {"domain": "example.com"}
    )
    result = json.loads(blocks[1]["result"])
    assert result["example.com"]["security_categories"] == ["Malware"]
    assert captured["path"] == "/investigate/v2/domains/categorization/example.com"
    assert captured["organization_id"] is None


@pytest.mark.asyncio
async def test_risk_score_and_whois_return_expected_shape():
    """TC7 (AC5): risk-score and WHOIS tools return the expected shape, no organization_id."""
    import json

    from mcp.server.fastmcp import FastMCP

    from cisco_umbrella_mcp.tools import investigate

    responses = {
        "/investigate/v2/domains/risk-score/example.com": {"risk_score": 12},
        "/investigate/v2/whois/example.com": {
            "domain": "example.com",
            "registrant": "Example Org",
            "registrar": "Example Registrar",
            "created": "1995-08-14",
            "updated": "2025-08-13",
            "expires": "2026-08-13",
            "nameServers": ["a.iana-servers.net", "b.iana-servers.net"],
        },
    }

    class _StubClient:
        async def get(self, path, params=None, organization_id=None):
            assert organization_id is None
            return responses[path]

    mcp = FastMCP(name="test")
    investigate.register(mcp, lambda: _StubClient())

    risk_blocks = await mcp.call_tool(
        "cisco_umbrella_get_domain_risk_score", {"domain": "example.com"}
    )
    assert isinstance(json.loads(risk_blocks[1]["result"])["risk_score"], int)

    whois_blocks = await mcp.call_tool("cisco_umbrella_get_domain_whois", {"domain": "example.com"})
    whois = json.loads(whois_blocks[1]["result"])
    assert {"domain", "registrant", "registrar", "nameServers"} <= set(whois)


@pytest.mark.asyncio
async def test_new_tools_return_not_configured_without_gateway_headers():
    """TC8 (AC6): missing gateway headers -> not_configured envelope, same as the existing tools."""
    import json

    from cisco_umbrella_mcp.config import Settings
    from cisco_umbrella_mcp.server import create_mcp_server

    mcp = create_mcp_server(Settings(auth_mode="gateway"))
    new_tool_calls = [
        ("cisco_umbrella_list_api_keys", {}),
        ("cisco_umbrella_list_destination_lists", {"organization_id": "1234567"}),
        (
            "cisco_umbrella_get_destination_list_destinations",
            {"organization_id": "1234567", "destination_list_id": "dl1"},
        ),
        ("cisco_umbrella_list_application_lists", {"organization_id": "1234567"}),
        ("cisco_umbrella_get_application_usage", {"organization_id": "1234567"}),
        ("cisco_umbrella_get_domain_categorization", {"domain": "example.com"}),
        ("cisco_umbrella_get_domain_risk_score", {"domain": "example.com"}),
        ("cisco_umbrella_get_domain_whois", {"domain": "example.com"}),
    ]
    for name, args in new_tool_calls:
        blocks = await mcp.call_tool(name, args)
        envelope = json.loads(blocks[1]["result"])
        assert envelope["error"]["code"] == "not_configured", f"{name}: {envelope}"


@pytest.mark.asyncio
async def test_new_tools_map_upstream_errors_to_envelope():
    """TC9 (AC7): upstream 403/404/429/5xx map to the existing error envelope, no stack trace."""
    import json

    from mcp.server.fastmcp import FastMCP

    from cisco_umbrella_mcp.api_client import UmbrellaError
    from cisco_umbrella_mcp.tools import admin, investigate, policies

    class _FailingClient:
        def __init__(self, status_code):
            self._status_code = status_code

        async def get(self, path, params=None, organization_id=None):
            raise UmbrellaError(self._status_code, "boom")

    cases = [
        (admin, "cisco_umbrella_list_api_keys", {}, 403),
        (policies, "cisco_umbrella_list_destination_lists", {"organization_id": "1"}, 404),
        (investigate, "cisco_umbrella_get_domain_risk_score", {"domain": "example.com"}, 429),
        (investigate, "cisco_umbrella_get_domain_whois", {"domain": "example.com"}, 500),
    ]
    for module, name, args, status_code in cases:
        mcp = FastMCP(name="test")
        module.register(mcp, lambda sc=status_code: _FailingClient(sc))
        blocks = await mcp.call_tool(name, args)
        text = blocks[1]["result"]
        envelope = json.loads(text)
        assert "code" in envelope["error"], f"{name}: {envelope}"
        assert "Traceback" not in text and "<html" not in text.lower()
