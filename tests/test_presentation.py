"""Tests for the core server functionality."""

import pytest
from pydantic import ValidationError

from jurismcp.presentation.mcp import StjLegalPrecedentsRequest


@pytest.mark.asyncio
async def test_listed_tools() -> None:
    """Test all listed tools."""
    from jurismcp.presentation.mcp import call_tool, list_tools

    tools = await list_tools()
    assert len(tools) > 0
    for tool in tools:
        assert tool.name is not None
        assert tool.description is not None
        assert tool.inputSchema is not None

        # Currently all tools expect one argument at least, thus it is expected that every tool
        # will raise a ValidationError if none are provided.
        with pytest.raises(ValidationError):
            await call_tool(tool.name, {})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        pytest.param(
            "invalid_tool",
            {},
            marks=pytest.mark.xfail(
                strict=True, reason="Invalid tool name", raises=AssertionError
            ),
            id="invalid_tool_name",
        ),
        pytest.param(
            StjLegalPrecedentsRequest.__name__,
            {"summary": "fraude execução"},
            id="valid_tool_call",
        ),
    ],
)
async def test_call_tool(
    tool_name: str,
    arguments: dict[str, str],
) -> None:
    """Test calling a server's tool.

    The purpose of this test is to ensure that the server is able to call the tool
    and return the correct results.

    There's no need to test the tools themselves, as they are tested in the domain's tests."""
    from pathlib import Path

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import TextContent

    async with (
        stdio_client(
            StdioServerParameters(
                command="uv",
                args=[
                    "--directory",
                    str(Path(__file__).parent.parent.absolute()),
                    "run",
                    "serve",
                ],
            )
        ) as (read, write),
        ClientSession(
            read_stream=read,
            write_stream=write,
        ) as client,
    ):
        await client.initialize()
        assert len((await client.list_tools()).tools) > 0

        results = await client.call_tool(tool_name, arguments)

    assert not results.isError
    assert isinstance(results.content, list)
    assert all(isinstance(content, TextContent) for content in results.content)
