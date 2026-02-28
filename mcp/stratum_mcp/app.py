"""
Shared FastMCP application instance.

This module is imported by tool modules so they can register tools on the
single shared MCP app instance. Import order matters: server.py must import
this module first, then import the tool modules so decorators fire.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Stratum Sports")
