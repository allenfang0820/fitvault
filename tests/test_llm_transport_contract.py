import ast
import inspect
import textwrap
import unittest

from main import Api


class _CallVisitor(ast.NodeVisitor):
    def __init__(self):
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(self._name(node.func))
        self.generic_visit(node)

    def _name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = self._name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""


def _called_names(fn) -> list[str]:
    source = textwrap.dedent(inspect.getsource(fn))
    tree = ast.parse(source)
    visitor = _CallVisitor()
    visitor.visit(tree)
    return visitor.calls


class TestLLMTransportContract(unittest.TestCase):
    def test_call_llm_uses_only_unified_generate_adapter_for_llm_text(self):
        calls = _called_names(Api.call_llm)

        self.assertIn("self._generate_llm_text", calls)
        self.assertNotIn("llm_backend.chat_completions", calls)
        self.assertNotIn("llm_backend._chat_completions_http", calls)
        self.assertNotIn("llm_backend.test_llm_connection", calls)
        self.assertNotIn("llm_backend.generate_text", calls)

    def test_generate_adapter_is_the_only_backend_generate_text_bridge(self):
        calls = _called_names(Api._generate_llm_text)

        self.assertEqual(calls.count("llm_backend.generate_text"), 1)
        self.assertNotIn("llm_backend.chat_completions", calls)
        self.assertNotIn("llm_backend._chat_completions_http", calls)

    def test_remote_fit_sync_uses_garmin_provider_not_llm_transport(self):
        calls = _called_names(Api.sync_remote_fit_activities)

        self.assertIn("garmin_sync.download_fit_json", calls)
        self.assertIn("self.sync_local_fit_files", calls)
        self.assertNotIn("llm_backend.chat_completions", calls)
        self.assertNotIn("self._generate_llm_text", calls)


if __name__ == "__main__":
    unittest.main()
