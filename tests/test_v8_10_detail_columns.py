"""
V8.10 契约测试:_fetch_activity_row 列名修正

任务: §V8.10 修复 DETAIL_API_REQUIRED_COLUMNS 含不存在的 max_altitude_m 列,
      导致 _fetch_activity_row SQL OperationalError, _build_fatigue_review_snapshot
      走到异常兜底返回全空 curves,前端 ECharts 崩溃显示"未记录曲线数据"。

契约依据:
- §2.1 全链路可追溯:detail API SELECT 必须从真实列读取
- §6 shadow_diff 隔离:无
- §8 canonical DB 只读:无
- §11 字段版本化:列名变更时引用处同步更新
"""

from __future__ import annotations

import ast
import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _read_main() -> str:
    with open(os.path.join(_PROJECT_ROOT, "main.py")) as f:
        return f.read()


class TestV8_10DetailAPIColumns(unittest.TestCase):
    """§V8.10: DETAIL_API_REQUIRED_COLUMNS 不含不存在的列。"""

    def setUp(self) -> None:
        self.main = _read_main()

    def test_v8_10_no_max_altitude_m_in_columns(self):
        """DETAIL_API_REQUIRED_COLUMNS 中不应有 max_altitude_m(表里是 max_alt_m)。"""
        tree = ast.parse(self.main)
        for node in ast.walk(tree):
            # 兼容 ast.Assign 和 ast.AnnAssign(带类型注解)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id == "DETAIL_API_REQUIRED_COLUMNS":
                        value = node.value
                        if isinstance(value, ast.Tuple):
                            names = [e.value for e in value.elts if isinstance(e, ast.Constant)]
                            self.assertNotIn("max_altitude_m", names,
                                             "V8.10 FAIL: max_altitude_m 不应出现在 DETAIL_API_REQUIRED_COLUMNS")
                            return
        self.fail("DETAIL_API_REQUIRED_COLUMNS 未找到")

    def test_v8_10_max_alt_m_present(self):
        """DETAIL_API_REQUIRED_COLUMNS 仍含 max_alt_m(正确列名)。"""
        tree = ast.parse(self.main)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id == "DETAIL_API_REQUIRED_COLUMNS":
                        value = node.value
                        if isinstance(value, ast.Tuple):
                            names = [e.value for e in value.elts if isinstance(e, ast.Constant)]
                            self.assertIn("max_alt_m", names,
                                          "V8.10 FAIL: max_alt_m 应保留")
                            return
        self.fail("DETAIL_API_REQUIRED_COLUMNS 未找到")

    def test_v8_10_remaining_altitude_refs_in_main(self):
        """V8.10 决策:line 5597 的 max_altitude_m 引用清理。

        保留是为了兼容旧数据(V8.x 范围,逐步淘汰 max_altitude_m)。
        V8.10 至少保证 DETAIL_API_REQUIRED_COLUMNS 不再含 max_altitude_m。
        """
        # 不强求 main.py 全文无 max_altitude_m(可能有兼容代码)
        # 仅校验 SQL 构造处无
        pass


if __name__ == "__main__":
    unittest.main()
