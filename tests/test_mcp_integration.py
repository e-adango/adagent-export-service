import unittest

from fastapi.testclient import TestClient

import main


class MCPIntegrationTests(unittest.TestCase):
    def test_mcp_initialize_and_tools_list(self) -> None:
        client = TestClient(main.app)
        initialize = client.post(
            "/mcp",
            headers={
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-06-18",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        self.assertEqual(initialize.status_code, 200)
        session_id = initialize.headers.get("Mcp-Session-Id")
        self.assertTrue(session_id)

        tools = client.post(
            "/mcp",
            headers={
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-06-18",
                "Mcp-Session-Id": session_id,
            },
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        self.assertEqual(tools.status_code, 200)
        payload = tools.json()
        self.assertIn("result", payload)
        self.assertGreaterEqual(len(payload["result"].get("tools", [])), 1)


if __name__ == "__main__":
    unittest.main()
