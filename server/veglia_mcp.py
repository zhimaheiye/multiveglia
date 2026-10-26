#!/usr/bin/env python3
"""
Veglia MCP Server (stdio transport).
Bridges Android companion state to LLMs / AI agents via Model Context Protocol (MCP SDK v2).
"""
from __future__ import annotations

import sys
import os
from mcp.server.auth.middleware.auth_context import get_access_token
from pathlib import Path
from mcp.server.mcpserver import MCPServer, Image
from mcp.types import CallToolResult, TextContent, ToolAnnotations

# Ensure stdout is reserved exclusively for JSON-RPC MCP messages.
# Never write arbitrary logs to stdout.

import veglia_tools

AUTH_PROVIDER = None
auth_options = {}
if os.environ.get('VEGLIA_HTTP_MODE') == '1':
    from mcp_auth import build_auth
    AUTH_PROVIDER, auth_settings = build_auth()
    auth_options = {'auth_server_provider': AUTH_PROVIDER, 'auth': auth_settings}


def require_scope(scope):
    if os.environ.get('VEGLIA_HTTP_MODE') == '1':
        token = get_access_token()
        if token is None or scope not in token.scopes:
            resource = AUTH_PROVIDER.resource if AUTH_PROVIDER else ''
            challenge = f'Bearer resource_metadata="{AUTH_PROVIDER.issuer}/.well-known/oauth-protected-resource/mcp", scope="veglia:read {scope}"'
            return CallToolResult(is_error=True, content=[TextContent(type='text', text='Additional authorization required: '+scope)], meta={'mcp/www_authenticate':[challenge]})
    return None

mcp = MCPServer(
    "veglia-phone",
    version="0.7.0",
    **auth_options,
    instructions=(
        "Tools for perceiving the owner's context through Veglia. "
        "Provides fused multi-device context (get_context), Android companion phone state "
        "(foreground apps, on-demand screenshots), and Windows computers state across devices "
        "in the Veglia Device Hub (active window, process, title, user idle time). "
        "Prefer get_context first for overall awareness of what the owner is currently doing and "
        "which device is active. Use get_devices_activity or get_phone_activity for lower-level details. "
        "Only use summon_phone_ai when the user explicitly requests it "
        "or an established automation policy authorizes it."
    )
)


@mcp.tool(
    name="get_veglia_status",
    meta={"securitySchemes": [{"type": "oauth2", "scopes": ['veglia:read']}]},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False),
    description="Check Veglia companion server reachability, version, and screenshot directory status. Useful for diagnostic health checks."
)
def get_veglia_status() -> dict:
    """Read Veglia server health and screenshot directory information."""
    denied = require_scope('veglia:read')
    if denied is not None:
        return denied
    result = veglia_tools.get_veglia_status_result()
    if os.environ.get('VEGLIA_HTTP_MODE') == '1':
        return {k: result[k] for k in ('ok', 'tool', 'server_reachable', 'service', 'version') if k in result}
    return result


@mcp.tool(
    name="get_phone_activity",
    meta={"securitySchemes": [{"type": "oauth2", "scopes": ['veglia:read']}]},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False),
    description="Read recent foreground application transitions on the owner's phone. Prefer this low-friction read to check what app the owner is currently using."
)
def get_phone_activity() -> dict:
    """Read recent foreground app events with friendly labels and elapsed time."""
    denied = require_scope('veglia:read')
    if denied is not None:
        return denied
    return veglia_tools.get_phone_activity_result()


@mcp.tool(
    name="get_phone_screen",
    meta={"securitySchemes": [{"type": "oauth2", "scopes": ['veglia:read', 'veglia:capture']}]},
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False),
    description="Capture an on-demand screenshot of the phone screen via accessibility service and return the image content directly for visual inspection."
)
def get_phone_screen(timeout: float = 10.0) -> Image:
    """Trigger accessibility screenshot and return the image data directly to the agent."""
    denied = require_scope('veglia:capture')
    if denied is not None:
        return denied
    res = veglia_tools.get_phone_screen_result(timeout=max(1.0, min(timeout, 30.0)))
    if not res.get("ok"):
        raise RuntimeError(res.get("error", "timeout_waiting_for_screenshot"))
    return Image(path=res["image_path"], format="jpeg")


@mcp.tool(
    name="summon_phone_ai",
    meta={"securitySchemes": [{"type": "oauth2", "scopes": ['veglia:read', 'veglia:summon']}]},
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False),
    description="Bring the target companion AI application to the foreground on the phone. This has noticeable side effects; call only when explicitly requested by the user or by an established automation rule."
)
def summon_phone_ai() -> dict:
    """Send summon signal to pull the companion AI app to the front."""
    denied = require_scope('veglia:summon')
    if denied is not None:
        return denied
    return veglia_tools.summon_phone_ai_result()


@mcp.tool(
    name="get_devices_activity",
    meta={"securitySchemes": [{"type": "oauth2", "scopes": ['veglia:read']}]},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False),
    description=(
        "Read activity status across all connected Windows computers in the Veglia Device Hub. "
        "Returns a list of known devices with online status, foreground process, window title, and idle seconds. "
        "Use this to see which computer the owner is using or check overall workspace activity."
    )
)
def get_devices_activity() -> dict:
    """Read summary activity for all registered devices."""
    denied = require_scope('veglia:read')
    if denied is not None:
        return denied
    return veglia_tools.get_devices_activity_result()


@mcp.tool(
    name="get_device_activity",
    meta={"securitySchemes": [{"type": "oauth2", "scopes": ['veglia:read']}]},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False),
    description=(
        "Read detailed activity for any registered Windows computer by its device_id. "
        "Use get_devices_activity first if available device IDs are unknown. "
        "Returns foreground process, window title, user idle time in seconds, and recent window switch history. "
        "Also reports whether the device is currently online (reported within 10s) and elapsed time since last report."
    )
)
def get_device_activity(device_id: str) -> dict:
    """Read detailed activity and switch history for a specific device."""
    denied = require_scope('veglia:read')
    if denied is not None:
        return denied
    return veglia_tools.get_device_activity_result(device_id)


@mcp.tool(
    name="get_desktop_activity",
    meta={"securitySchemes": [{"type": "oauth2", "scopes": ['veglia:read']}]},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False),
    description=(
        "Read current Windows desktop state for the default/local desktop PC: "
        "foreground process name, window title, user idle time in seconds, and recent window-switch history. "
        "Backwards-compatibility tool querying the central Device Hub for the primary desktop."
    )
)
def get_desktop_activity() -> dict:
    """Return default desktop PC foreground app, idle seconds, and recent window switch history."""
    denied = require_scope('veglia:read')
    if denied is not None:
        return denied
    return veglia_tools.get_desktop_activity_result()


@mcp.tool(
    name="get_context",
    meta={"securitySchemes": [{"type": "oauth2", "scopes": ['veglia:read']}]},
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False),
    description=(
        "Return a deterministic fused snapshot of the owner's current multi-device activity, "
        "including active devices, likely primary device, simultaneous usage and ambiguity. "
        "Use this before manually comparing individual devices when the question concerns the owner's overall current context."
    )
)
def get_context() -> dict:
    """Return fused multi-device context snapshot across phone and connected computers."""
    denied = require_scope('veglia:read')
    if denied is not None:
        return denied
    return veglia_tools.get_context_result()


if __name__ == "__main__":
    mcp.run(transport="stdio")
