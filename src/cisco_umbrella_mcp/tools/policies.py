"""Cisco Umbrella Policies v2 tools (Destination Lists, Application Lists).

Tool naming convention: cisco_umbrella_<action>_<resource>

PRD-21226: added to close the "policies" gap. Cisco's Policies v2 API has
no single "list security-policy objects" endpoint reachable from this
change's research; destination lists and application lists are what an
Umbrella admin actually configures as policy in the console, so they are
the "policies" deliverable here (design doc OQ1). If a dedicated
policy-object endpoint is confirmed later, add it alongside these without
changing this module's shape.
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

_MAX_LIMIT = 200

# Same wording and same reasoning as reports.py's _ORG_ID_DESC: required,
# not optional, because a parent-scope call answers 200 with either
# nothing or the parent's own data — indistinguishable downstream from
# "this customer has no policy objects".
_ORG_ID_DESC = (
    "Required. The managed customer's organization ID — resolve via "
    "cisco_umbrella_list_customers, never guess one."
)


def register(mcp: FastMCP, client_factory: Callable[[], UmbrellaClient | None]) -> None:
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def cisco_umbrella_list_destination_lists(
        organization_id: Annotated[str, Field(description=_ORG_ID_DESC)],
        limit: Annotated[
            int, Field(description="Max results per page (default 100, hard cap 200).", ge=1)
        ] = 100,
        offset: Annotated[int | None, Field(description="Pagination offset.", ge=0)] = None,
    ) -> str:
        """List this customer's destination lists (named allow/block domain groups).

        One of the two policy object types this connector exposes (the
        other is application lists) — see README Known Gaps for why.
        Use cisco_umbrella_get_destination_list_destinations for the
        domains/URLs inside one list.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        limit = min(limit, _MAX_LIMIT)
        params = {"limit": limit, "offset": offset}
        try:
            result = await client.get(
                "/policies/v2/destinationlists",
                params=params,
                organization_id=organization_id,
            )
            return dump_json_capped(result)
        except UmbrellaError as e:
            return e.to_envelope()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def cisco_umbrella_get_destination_list_destinations(
        organization_id: Annotated[str, Field(description=_ORG_ID_DESC)],
        destination_list_id: Annotated[
            str,
            Field(
                description=(
                    "Required. A destination list's id, from "
                    "cisco_umbrella_list_destination_lists."
                )
            ),
        ],
        limit: Annotated[
            int, Field(description="Max results per page (default 100, hard cap 200).", ge=1)
        ] = 100,
        offset: Annotated[int | None, Field(description="Pagination offset.", ge=0)] = None,
    ) -> str:
        """List the domains/URLs inside one destination list.

        Resolve destination_list_id via
        cisco_umbrella_list_destination_lists first — don't guess one.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        limit = min(limit, _MAX_LIMIT)
        params = {"limit": limit, "offset": offset}
        try:
            result = await client.get(
                f"/policies/v2/destinationlists/{quote(destination_list_id, safe='')}/destinations",
                params=params,
                organization_id=organization_id,
            )
            return dump_json_capped(result)
        except UmbrellaError as e:
            return e.to_envelope()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def cisco_umbrella_list_application_lists(
        organization_id: Annotated[str, Field(description=_ORG_ID_DESC)],
    ) -> str:
        """List this customer's application lists (named groups of apps used in policy).

        The other policy object type this connector exposes, alongside
        destination lists. Pair with
        cisco_umbrella_get_application_usage for per-app traffic counts.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.get(
                "/policies/v2/applicationLists",
                organization_id=organization_id,
            )
            return dump_json_capped(result)
        except UmbrellaError as e:
            return e.to_envelope()

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def cisco_umbrella_get_application_usage(
        organization_id: Annotated[str, Field(description=_ORG_ID_DESC)],
    ) -> str:
        """Get per-application usage counts for this customer.

        Use alongside cisco_umbrella_list_application_lists to see which
        apps are grouped into which application list.
        """
        client = client_factory()
        if client is None:
            return NO_TOKEN
        try:
            result = await client.get(
                "/policies/v2/applications/usage",
                organization_id=organization_id,
            )
            return dump_json_capped(result)
        except UmbrellaError as e:
            return e.to_envelope()
