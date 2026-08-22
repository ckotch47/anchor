from __future__ import annotations

import unittest
from unittest.mock import patch

from anchor.cli_serve import UI_HTML, serve, validate_serve_host


class CliServeTest(unittest.TestCase):
    def test_only_loopback_hosts_are_accepted(self) -> None:
        for host in ("localhost", "127.0.0.1", "::1"):
            with self.subTest(host=host):
                validate_serve_host(host)
        for host in ("0.0.0.0", "192.168.1.10", "anchor.internal"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                validate_serve_host(host)

    def test_rejected_host_has_no_startup_side_effects(self) -> None:
        with patch("anchor.cli_serve.build_container") as build_container:
            with patch("anchor.cli_serve.webbrowser.open") as open_browser:
                with patch("anchor.cli_serve.mcp_app.run") as run:
                    with self.assertRaises(ValueError):
                        serve(host="0.0.0.0")

        build_container.assert_not_called()
        open_browser.assert_not_called()
        run.assert_not_called()

    def test_web_ui_scopes_nested_task_and_link_reads(self) -> None:
        self.assertNotIn("mcpCallTool('links_list', {", UI_HTML)
        self.assertNotIn("mcpCallTool('tasks_get', {", UI_HTML)
        self.assertNotIn("mcpCallTool('notes_get', {", UI_HTML)
        self.assertIn("Select a project before using project-scoped tools", UI_HTML)
        self.assertNotIn("limit:200", UI_HTML)
        self.assertIn("mcpCallTool('tasks_list', withProject({ limit:100", UI_HTML)

    def test_web_ui_escapes_diagnostic_and_structured_payloads_before_inner_html(self) -> None:
        self.assertNotIn("${e.message}", UI_HTML)
        self.assertNotIn("'+e.message+'", UI_HTML)
        self.assertIn("esc(JSON.stringify(data.data||data, null, 2))", UI_HTML)
        self.assertIn("esc(JSON.stringify(tool.inputSchema, null, 2))", UI_HTML)
        self.assertIn("esc(currentProject||'(none selected)')", UI_HTML)


if __name__ == "__main__":
    unittest.main()
