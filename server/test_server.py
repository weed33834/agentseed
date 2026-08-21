"""AgentSeed MCP server protocol tests (spawns the real stdio server)."""

import json
import os
import subprocess
import sys
import unittest

SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard_server.py")


class TestServerProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc = subprocess.Popen(
            [sys.executable, SERVER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.stdin.close()
            cls.proc.wait(timeout=10)

    def _rpc(self, payload: dict) -> dict:
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        self.assertTrue(line.strip(), "server closed the stream unexpectedly")
        return json.loads(line)

    def test_initialize_reports_version(self):
        r = self._rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2024-11-05", "capabilities": {}}})
        self.assertEqual(r["result"]["serverInfo"]["version"], "1.3.3")

    def test_ping_returns_empty_result(self):
        r = self._rpc({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        self.assertEqual(r["result"], {})

    def test_unknown_method_is_error_32601(self):
        r = self._rpc({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
        self.assertEqual(r["error"]["code"], -32601)
        self.assertNotIn("result", r)

    def test_tools_list_and_call(self):
        r = self._rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
        names = {t["name"] for t in r["result"]["tools"]}
        self.assertEqual(names, {"verify_code", "scan_hallucination",
                                 "check_plugin", "sandbox_run", "schema_validate"})
        r = self._rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                       "params": {"name": "scan_hallucination",
                                  "arguments": {"source": "from unittest.mock import Mock\n"}}})
        result = json.loads(r["result"]["content"][0]["text"])
        self.assertTrue(result["clean"])


if __name__ == "__main__":
    unittest.main()
