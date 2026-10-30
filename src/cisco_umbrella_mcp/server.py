import contextvars
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ._json import dump_json_capped
from .api_client import UmbrellaClient, UmbrellaError
from .config import Settings
from .tools._common import NO_TOKEN

# ─────────────────────────────────────────────────────────────────────────────
# Per-request credential contextvar for gateway mode.
# GatewayTokenMiddleware sets this before the MCP handler runs.
# Python asyncio copies context per task, so concurrent requests are isolated.
# ─────────────────────────────────────────────────────────────────────────────
_gateway_creds_var: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "umbrella_gateway_creds", default=None
)


def get_client_from_context(settings: Settings) -> UmbrellaClient | None:
    """Resolve the active UmbrellaClient for the current request context."""
    if settings.auth_mode == "gateway":
        creds = _gateway_creds_var.get()
        if creds is None:
            return None
        api_key, key_secret = creds
    else:
        api_key = settings.umbrella_api_key
        key_secret = settings.umbrella_key_secret

    if not api_key or not key_secret:
        return None
    return UmbrellaClient(api_key, key_secret)


class GatewayTokenMiddleware:
    """ASGI middleware for gateway mode.

    Reads the configured API key + key secret headers from each request and
    stores them in the contextvar for the duration of that request. Returns
    401 if either header is missing on /mcp requests.
    """

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        # Header lookup is case-insensitive in Starlette
        api_key = request.headers.get(self.settings.umbrella_api_key_header.lower())
        key_secret = request.headers.get(self.settings.umbrella_key_secret_header.lower())
        if not api_key or not key_secret:
            response = JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": (
                        f"Gateway mode requires the {self.settings.umbrella_api_key_header} and "
                        f"{self.settings.umbrella_key_secret_header} headers"
                    ),
                    "required_headers": [
                        self.settings.umbrella_api_key_header,
                        self.settings.umbrella_key_secret_header,
                    ],
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return

        ctx_token = _gateway_creds_var.set((api_key, key_secret))
        try:
            await self.app(scope, receive, send)
        finally:
            _gateway_creds_var.reset(ctx_token)


def create_mcp_server(settings: Settings) -> FastMCP:
    """Build the FastMCP server instance and register all tools."""
    # DNS-rebinding protection is disabled because the container runs behind
    # mcp-gateway on an internal Docker network and is never publicly exposed.
    mcp = FastMCP(
        name="cisco-umbrella-mcp",
        instructions=(
            "Cisco Umbrella is a DNS-layer cloud security platform: it blocks "
            "malicious domains, filters web content by category, and logs "
            "network activity (DNS, proxy/SWG, firewall, AMP retrospective "
            "malware reclassification) for a customer's network and roaming "
            "endpoints. This credential is a Managed Provider (MSSP) parent "
            "key, so every customer-scoped tool requires organization_id — "
            "resolve one via list_customers, then pass it to every other "
            "customer-scoped tool. Covers: activity reports (get_activity_dns/"
            "_proxy/_firewall/_activity_amp_retrospective), category counts "
            "(get_categories then get_summaries_by_category with security "
            "category ids — unfiltered drops them), deployment inventory "
            "(list_networks/_roaming_computers/_virtual_appliances), app "
            "discovery (list_applications/_protocols/_application_categories, "
            "may 403 if unlicensed), policy objects (list_destination_lists, "
            "get_destination_list_destinations, list_application_lists, "
            "get_application_usage), account API keys (list_api_keys — no "
            "secret ever returned), and global domain threat intel with no "
            "organization_id (get_domain_categorization, get_domain_risk_score, "
            "get_domain_whois). Provider-level (no organization_id): "
            "list_customers, get_providers_console, list_api_keys. All tools "
            "are read-only; there are no write or delete tools."
        ),
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
        json_response=True,
    )

    def client_factory() -> UmbrellaClient | None:
        return get_client_from_context(settings)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def cisco_umbrella_test_connection() -> str:
        """Verify Cisco Umbrella credentials for the current request are usable.

        Resolves the credential from the active request context (gateway
        headers, or env vars in local single-tenant mode) and makes a
        lightweight live call to confirm the API accepts it. Use this before
        other tools if you're unsure the configured credential works.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.get("/reports/v2/providers/consoles")
            return dump_json_capped({"status": "ok", "provider_console": result})
        except UmbrellaError as e:
            return e.to_envelope()

    if not settings.has_credentials:
        print(
            "Warning: No Cisco Umbrella credentials found. Report tools will "
            "return not_configured errors until credentials are supplied.",
            file=sys.stderr,
        )

    # Register all tool modules here.
    from .tools import admin, investigate, policies, reports

    reports.register(mcp, client_factory)
    admin.register(mcp, client_factory)
    policies.register(mcp, client_factory)
    investigate.register(mcp, client_factory)

    return mcp
