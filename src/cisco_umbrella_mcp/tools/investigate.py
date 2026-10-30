"""Cisco Umbrella Investigate tools (global domain threat intelligence).

Tool naming convention: cisco_umbrella_<action>_<resource>

PRD-21226: added to close the "investigations" gap. Unlike every other
tool module in this server, these three are not organization_id-scoped:
Investigate is Cisco's global threat-intel dataset keyed by domain, not
per-managed-customer data (design doc OQ3) — matching how
reports.cisco_umbrella_list_customers / get_providers_console already
skip organization_id for the same "this isn't customer data" reason.

Host/auth assumption (design doc OQ2): these calls are assumed reachable
at the same https://api.umbrella.com host, via the same OAuth2
client_credentials key/secret pair as every other tool (Cisco's docs note
the legacy investigate.api.umbrella.com host "was moved to the legacy
Umbrella API", implying consolidation). This could not be re-confirmed
against a live account or the vendor's current API reference during this
change — docs.umbrella.com's reference pages now redirect to a generic
landing page (securitydocs.cisco.com), and no test account was available
(see README Known Gaps). If that assumption is wrong, only this module's
base host/auth needs to change — the per-request credential/error
handling is unaffected.
"""

from collections.abc import Callable
from typing import Annotated
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped
from ..api_client import UmbrellaClient, UmbrellaError
from ._common import NO_TOKEN

_DOMAIN_DESC = 'Required. The domain name to look up, e.g. "example.com".'


def register(mcp: FastMCP, client_factory: Callable[[], UmbrellaClient | None]) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def cisco_umbrella_get_domain_categorization(
        domain: Annotated[str, Field(description=_DOMAIN_DESC)],
        showlabels: Annotated[
            bool,
            Field(description="Include human-readable category labels alongside the numeric ids."),
        ] = True,
    ) -> str:
        """Get Cisco's security/content categorization for a domain.

        Global Investigate threat-intel lookup — no organization_id,
        unlike every customer-scoped tool in this server (see module
        docstring).
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        params = {"showLabels": showlabels}
        try:
            result = await client.get(
                f"/investigate/v2/domains/categorization/{quote(domain, safe='')}",
                params=params,
            )
            return dump_json_capped(result)
        except UmbrellaError as e:
            return e.to_envelope()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def cisco_umbrella_get_domain_risk_score(
        domain: Annotated[str, Field(description=_DOMAIN_DESC)],
    ) -> str:
        """Get Cisco's numeric risk score (0-100) for a domain.

        Global Investigate lookup — no organization_id (see module
        docstring).
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            path = f"/investigate/v2/domains/risk-score/{quote(domain, safe='')}"
            result = await client.get(path)
            return dump_json_capped(result)
        except UmbrellaError as e:
            return e.to_envelope()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def cisco_umbrella_get_domain_whois(
        domain: Annotated[str, Field(description=_DOMAIN_DESC)],
    ) -> str:
        """Get the current WHOIS record for a domain.

        Global Investigate lookup — no organization_id (see module
        docstring).
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.get(f"/investigate/v2/whois/{quote(domain, safe='')}")
            return dump_json_capped(result)
        except UmbrellaError as e:
            return e.to_envelope()
