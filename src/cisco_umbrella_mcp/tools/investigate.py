"""Cisco Umbrella Investigate tools (global domain threat intelligence).

Tool naming convention: cisco_umbrella_<action>_<resource>

PRD-21226: added to close the "investigations" gap. Unlike every other
tool module in this server, this tool is not organization_id-scoped:
Investigate is Cisco's global threat-intel dataset keyed by domain, not
per-managed-customer data (design doc OQ3) — matching how
reports.cisco_umbrella_list_customers / get_providers_console already
skip organization_id for the same "this isn't customer data" reason.

PRD-21226 review round 1 (must-fix): the three per-aspect GETs
(categorization, risk-score, WHOIS) are consolidated into one
cisco_umbrella_get_domain_intel(domain, aspect) tool rather than three
separate tools, to stay within the SOP's <=20 reference tool budget
(vendor-mcp-development-sop.md SS2.1). All three are single-domain-keyed
GETs with no other required parameter and no organization_id scoping, so
an "aspect" discriminator reads as one capability ("look up what Cisco
knows about this domain") rather than three unrelated ones — see
docs/tickets/PRD-21226.md "Option analysis" for the full reasoning.

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
from typing import Annotated, Literal
from urllib.parse import quote

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped
from ..api_client import UmbrellaClient, UmbrellaError
from ._common import NO_TOKEN

_DOMAIN_DESC = 'Required. The domain name to look up, e.g. "example.com".'

_ASPECT_TO_PATH = {
    "categorization": "/investigate/v2/domains/categorization/{domain}",
    "risk_score": "/investigate/v2/domains/risk-score/{domain}",
    "whois": "/investigate/v2/whois/{domain}",
}


def register(mcp: FastMCP, client_factory: Callable[[], UmbrellaClient | None]) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def cisco_umbrella_get_domain_intel(
        domain: Annotated[str, Field(description=_DOMAIN_DESC)],
        aspect: Annotated[
            Literal["categorization", "risk_score", "whois"],
            Field(
                description=(
                    'Which Investigate lookup to run: "categorization" (security/'
                    'content category ids, honors showlabels), "risk_score" '
                    "(numeric 0-100 risk score), or \"whois\" (current WHOIS record)."
                )
            ),
        ],
        showlabels: Annotated[
            bool,
            Field(
                description=(
                    "Only used when aspect=\"categorization\": include "
                    "human-readable category labels alongside the numeric ids. "
                    "Ignored for the other two aspects."
                )
            ),
        ] = True,
    ) -> str:
        """Get Cisco's global Investigate threat intel for a domain.

        Global lookup — no organization_id, unlike every customer-scoped
        tool in this server (see module docstring). One tool, three
        aspects: categorization (security/content categories), risk_score
        (0-100), or whois (current WHOIS record).
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        path = _ASPECT_TO_PATH[aspect].format(domain=quote(domain, safe=""))
        params = {"showLabels": showlabels} if aspect == "categorization" else None
        try:
            result = await client.get(path, params=params)
            return dump_json_capped(result)
        except UmbrellaError as e:
            return e.to_envelope()
