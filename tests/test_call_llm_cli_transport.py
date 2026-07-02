from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from main import Api  # noqa: E402


class TestCallLlmCliTransport(unittest.TestCase):
    def test_ordinary_chat_cli_transport_does_not_require_http_url_or_model(self):
        api = Api()
        captured = {}

        def fake_generate_text(**kwargs):
            captured.update(kwargs)
            return "CLI 回复"

        with patch("llm_backend.load_llm_config", return_value={
            "transport": "cli",
            "cli_type": "codex",
            "url": "",
            "model": "",
            "provider": "local_mcp",
        }), patch("llm_backend.generate_text", side_effect=fake_generate_text):
            res = api.call_llm("今天怎么训练?", "running")

        self.assertTrue(res["ok"])
        self.assertEqual(res["content"], "CLI 回复")
        self.assertEqual(captured["config"]["transport"], "cli")
        self.assertEqual(captured["config"]["cli_type"], "codex")
        self.assertEqual(captured["session_id"], api._session_id)
        self.assertEqual(api._chat_messages[-1], {"role": "assistant", "content": "CLI 回复"})

    def test_ordinary_chat_cli_requires_cli_type(self):
        api = Api()

        with patch("llm_backend.load_llm_config", return_value={
            "transport": "cli",
            "cli_type": "",
            "url": "",
            "model": "",
        }), patch("llm_backend.generate_text") as generate_text:
            res = api.call_llm("今天怎么训练?", "running")

        self.assertFalse(res["ok"])
        self.assertIn("CLI 类型未配置", res["error"])
        generate_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
