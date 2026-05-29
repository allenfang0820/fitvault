import unittest
from unittest import mock

import llm_backend
from main import Api


class TestLLMConfigRedaction(unittest.TestCase):
    def test_redact_llm_config_masks_api_key(self):
        redacted = llm_backend.redact_llm_config({"api_key": "sk-secret-123456", "provider": "openai"})

        self.assertEqual(redacted["api_key"], "")
        self.assertTrue(redacted["has_api_key"])
        self.assertEqual(redacted["api_key_masked"], "****3456")
        self.assertNotIn("sk-secret-123456", str(redacted))

    def test_get_llm_config_does_not_return_full_api_key(self):
        with mock.patch.object(llm_backend, "load_llm_config", return_value={
            "provider": "openai",
            "url": "https://example.test/v1/chat/completions",
            "model": "gpt-test",
            "api_key": "sk-live-secret-value",
            "agent_id": "agent-1",
            "watch_brand": "garmin",
            "local_dir": "/tmp/tracks",
        }):
            config = Api().get_llm_config()

        self.assertTrue(config["ok"])
        self.assertEqual(config["code"], 0)
        self.assertEqual(config["msg"], "ok")
        self.assertIn("data", config)
        self.assertIn("traceId", config)
        self.assertEqual(config["api_key"], "")
        self.assertEqual(config["data"]["api_key"], "")
        self.assertTrue(config["has_api_key"])
        self.assertEqual(config["api_key_masked"], "****alue")
        self.assertNotIn("sk-live-secret-value", str(config))


if __name__ == "__main__":
    unittest.main()
