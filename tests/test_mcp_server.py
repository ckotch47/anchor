from __future__ import annotations

import asyncio
import unittest

from anchor.mcp_server import mcp_app


class McpServerTest(unittest.TestCase):
    def test_mcp_exposes_core_tools(self) -> None:
        async def run() -> list[str]:
            tools = await mcp_app.list_tools()
            return [tool.name for tool in tools]

        tool_names = asyncio.run(run())

        self.assertIn("health", tool_names)
        self.assertIn("search", tool_names)
        self.assertIn("notes_add", tool_names)
        self.assertIn("history_append", tool_names)
        self.assertIn("history_update", tool_names)
        self.assertIn("history_search", tool_names)
        self.assertIn("history_delete", tool_names)
        self.assertIn("tasks_add", tool_names)
        self.assertIn("files_index", tool_names)
        self.assertIn("files_search", tool_names)
