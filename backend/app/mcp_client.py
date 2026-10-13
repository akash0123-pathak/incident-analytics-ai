"""Local MCP client used by the FastAPI application.

Each call starts the colocated stdio MCP server, so the normal local product
path is FastAPI -> MCP client -> MCP server -> governed data layer -> DuckDB.
This keeps the web app and external MCP clients on the same tool contract.
"""
import asyncio
import json
import os
import sys
from threading import Lock
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Every local API request starts a short-lived stdio MCP server. DuckDB on
# Windows permits a single process to open this database at a time, including
# read-only opens, so serialise those child-server calls at the FastAPI edge.
_MCP_CALL_LOCK = Lock()


async def _call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    # Uvicorn may be started from either the backend directory or the project
    # root. Give the spawned MCP server an explicit import path in both cases.
    backend_dir = Path(__file__).resolve().parent.parent
    environment = os.environ.copy()
    existing_path = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(backend_dir) + (os.pathsep + existing_path if existing_path else "")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        env=environment,
    )
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments or {})
    if result.isError:
        detail = "; ".join(getattr(item, "text", str(item)) for item in result.content)
        raise RuntimeError(f"MCP tool '{name}' failed: {detail}")
    text = "".join(getattr(item, "text", "") for item in result.content)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # FastMCP may serialize a list return value as adjacent JSON objects
        # in separate text content blocks. Decode that JSON stream into the
        # original list instead of treating it as a malformed single object.
        values = []
        decoder = json.JSONDecoder()
        position = 0
        try:
            while position < len(text):
                while position < len(text) and text[position].isspace():
                    position += 1
                if position >= len(text):
                    break
                value, position = decoder.raw_decode(text, position)
                values.append(value)
            if values:
                return values
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"MCP tool '{name}' returned invalid JSON") from exc


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Synchronously call a local MCP tool from FastAPI's worker thread.

    Uvicorn's reload process can install a Windows selector event loop, which
    cannot create subprocesses. Stdio MCP requires one, so construct a
    Proactor loop explicitly for this short-lived local client call.
    """
    with _MCP_CALL_LOCK:
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(_call_tool(name, arguments))
            finally:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
                asyncio.set_event_loop(None)
        return asyncio.run(_call_tool(name, arguments))
