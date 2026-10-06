"""Errors that MCP tools may return to the client."""


class ToolError(RuntimeError):
    """Expected error that is safe to return to an MCP client."""
