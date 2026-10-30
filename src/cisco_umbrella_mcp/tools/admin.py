"""Cisco Umbrella Admin API Key tools.

Tool naming convention: cisco_umbrella_<action>_<resource>

PRD-21226: added to close the "admin settings" gap — this account's own
API key inventory, not the managed-customer roster (that's
reports.cisco_umbrella_list_customers).
"""

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .._json import dump_json_capped
from ..api_client import UmbrellaClient, UmbrellaError
from ._common import NO_TOKEN


def register(mcp: FastMCP, client_factory: Callable[[], UmbrellaClient | None]) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def cisco_umbrella_list_api_keys() -> str:
        """List this Umbrella account's API keys (Admin > API Keys).

        Provider-level, like list_customers: no organization_id — this
        describes the credential itself, not a managed customer. Returns
        key metadata only (id, label, scope, status); Cisco never returns
        a key's secret after creation. Pagination could not be confirmed
        this change (see README Known Gaps) — takes no parameters.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.get("/admin/v2/apiKeys")
            return dump_json_capped(result)
        except UmbrellaError as e:
            return e.to_envelope()
