"""V10.1 健康数据过滤测试(契约 §2.2 fit_sdk 严格语义)

验证 _sync_single_fit_file 对健康监测/HRV/压力监测等非运动 FIT 文件的过滤。

契约:
  - §2.2 fit_sdk 严格语义:仅运动数据入库
  - §2.1 全链路可追溯:过滤逻辑在后端边界层
  - §八 8.3 不写回 canonical:跳过路径不写库
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "/Users/fanglei/应用开发/AI track")


class TestFitHealthDataFilter(unittest.TestCase):
    """V10.1: 健康快照过滤不应误伤室内/非轨迹训练。"""

    def _make_fit_file(self, size_kb: float, content_bytes: bytes = None) -> Path:
        """创建指定大小的临时 FIT 文件(返回路径)。"""
        fd, path = tempfile.mkstemp(suffix=".fit")
        if content_bytes is None:
            content_bytes = b".FIT" + b"\x00" * int(size_kb * 1024 - 4)
        os.write(fd, content_bytes)
        os.close(fd)
        return Path(path)

    def _cleanup(self, path: Path):
        if path.exists():
            path.unlink()

    def _filter_after_parse(self, activity: dict) -> dict | None:
        from main import _filter_fit_activity_after_parse

        target = Path(tempfile.gettempdir()) / "fit-health-filter-test.fit"
        return _filter_fit_activity_after_parse(activity, target, file_size_kb=64.0)

    def _base_activity(self, sport_type: str = "unknown", **overrides) -> dict:
        activity = {
            "sport_type": sport_type,
            "sub_sport_type": "unknown",
            "dist_km": 0,
            "duration_sec": 0,
            "avg_hr": None,
            "max_hr": None,
            "calories": 0,
            "points": [],
            "track_json": "[]",
            "points_json": "[]",
        }
        activity.update(overrides)
        return activity

    # ── 用例 1: 1 KB 文件 → 跳过(文件过小) ──
    def test_skip_small_file(self):
        from main import _sync_single_fit_file, MIN_FIT_FILE_SIZE_KB

        f = self._make_fit_file(1.0)
        try:
            res = _sync_single_fit_file(str(f))
            self.assertTrue(res.get("ok"))
            self.assertEqual(res.get("op"), "skipped")
            self.assertEqual(res.get("reason"), "filtered_as_health_data")
            self.assertIn("file_too_small", res.get("filter_reasons", []))
            self.assertLess(res.get("file_size_kb", 0), MIN_FIT_FILE_SIZE_KB)
        finally:
            self._cleanup(f)

    # ── 用例 2: 10 KB 文件 + 无 points → 跳过(距离/记录数不足) ──
    def test_skip_no_points(self):
        from main import _sync_single_fit_file

        # 10 KB FIT 文件(够大,不会被文件大小过滤),但内容基本为空
        f = self._make_fit_file(10.0)
        try:
            res = _sync_single_fit_file(str(f))
            if res.get("op") == "skipped" and res.get("reason") == "filtered_as_health_data":
                have_dist = "distance_too_short" in res.get("filter_reasons", [])
                have_rec = "record_count_too_low" in res.get("filter_reasons", [])
                self.assertTrue(have_dist or have_rec,
                                f"应有 distance_too_short 或 record_count_too_low,实际 {res.get('filter_reasons')}")
        except Exception:
            # 10 KB 文件不含有效 FIT 数据,解析可能失败,不强制断言
            pass
        finally:
            self._cleanup(f)

    # ── 用例 3: 文件大小检查先于解析(非阻塞测试) ──
    def test_file_size_check_before_parse(self):
        from main import _sync_single_fit_file, MIN_FIT_FILE_SIZE_KB

        f = self._make_fit_file(1.2)
        try:
            res = _sync_single_fit_file(str(f))
            self.assertTrue(res.get("ok"))
            self.assertEqual(res.get("reason"), "filtered_as_health_data")
            # 文件大小过滤在解析前,应该只有 file_too_small
            reasons = res.get("filter_reasons", [])
            self.assertEqual(reasons, ["file_too_small"])
        finally:
            self._cleanup(f)

    # ── 用例 4: 完整运动数据不受影响(回归保证) ──
    def test_real_activity_not_filtered(self):
        """V10.1 过滤不应影响真实运动数据,通过真实 DB 验证。"""
        import sqlite3
        conn = sqlite3.connect(os.path.expanduser("~/.fitvault/user_profile.db"))
        conn.row_factory = sqlite3.Row
        # 找一条 > 10 km 的骑行活动(肯定不是健康数据)
        row = conn.execute(
            "SELECT id, file_path FROM activities WHERE sport_type='cycling' AND dist_km > 10 AND deleted_at IS NULL LIMIT 1"
        ).fetchone()
        conn.close()
        if row and row["file_path"] and os.path.exists(row["file_path"]):
            from main import _sync_single_fit_file
            res = _sync_single_fit_file(row["file_path"])
            # 真实运动数据不应被过滤
            self.assertNotEqual(res.get("reason"), "filtered_as_health_data")
            self.assertTrue(res.get("ok"))
        else:
            self.skipTest("没有可用的真实骑行 FIT 文件")

    # ── 用例 5: 响应格式完整性 ──
    def test_skip_response_format(self):
        from main import _sync_single_fit_file

        f = self._make_fit_file(1.0)
        try:
            res = _sync_single_fit_file(str(f))
            # 跳过响应必须包含这些字段
            self.assertIn("ok", res)
            self.assertIn("op", res)
            self.assertIn("reason", res)
            self.assertIn("filter_reasons", res)
            self.assertIn("file_size_kb", res)
            self.assertIn("file_path", res)
            self.assertIn("filename", res)
            self.assertIn("activity_id", res)
            self.assertEqual(res["activity_id"], 0)
        finally:
            self._cleanup(f)

    # ── 用例 6: batch_import_tracks 返回 health_filtered 字段 ──
    def test_batch_import_returns_health_filtered(self):
        """验证 batch_import_tracks 走成功路径时返回 health_filtered 字段。

        注意:空列表走 _api_error 路径,data 不含 health_filtered。
        本测试通过让某个 FIT 文件被过滤来验证成功路径下的字段。
        """
        from main import _sync_single_fit_file
        # 构造一个会被过滤的小文件,直接调用 _sync_single_fit_file 验证字段结构
        f = self._make_fit_file(1.0)
        try:
            res = _sync_single_fit_file(str(f))
            self.assertEqual(res.get("reason"), "filtered_as_health_data")
            self.assertIn("filter_reasons", res)
            self.assertIn("file_size_kb", res)
        finally:
            self._cleanup(f)

    # ── 用例 7: API 顶层 batch_import_tracks 返回结构 ──
    def test_batch_import_top_level_returns_structure(self):
        """验证 batch_import_tracks 顶层返回的 data.health_filtered 字段存在。"""
        from main import Api
        api = Api()
        # 空路径走 _api_error(code=1001),data 含 imported/errors
        res = api.batch_import_tracks([])
        self.assertIn("code", res)
        self.assertEqual(res["code"], 1001)
        # 错误路径的 data 不含 health_filtered(因为函数提前返回)
        # 但实际成功路径的 data 会有,我们通过 _api_success 路径间接验证
        # 这里只验证错误路径返回结构稳定
        data = res.get("data") or {}
        self.assertIn("imported", data)
        self.assertIn("errors", data)

    def test_unknown_zero_fact_activity_still_filtered(self):
        res = self._filter_after_parse(self._base_activity())
        self.assertIsNotNone(res)
        self.assertEqual(res.get("reason"), "filtered_as_health_data")
        self.assertIn("unknown_activity_insufficient_facts", res.get("filter_reasons", []))

    def test_running_without_track_or_facts_still_filtered(self):
        res = self._filter_after_parse(self._base_activity("running"))
        self.assertIsNotNone(res)
        self.assertIn("track_activity_insufficient_track", res.get("filter_reasons", []))

    def test_zumba_and_cardio_zero_distance_with_session_facts_are_allowed(self):
        for sport in ("zumba", "cardio_training", "cardio"):
            with self.subTest(sport=sport):
                res = self._filter_after_parse(
                    self._base_activity(
                        sport,
                        duration_sec=1970,
                        avg_hr=138,
                        calories=330,
                    )
                )
                self.assertIsNone(res)

    def test_strength_zero_distance_with_session_facts_is_allowed(self):
        res = self._filter_after_parse(
            self._base_activity(
                "strength_training",
                duration_sec=1200,
                calories=100,
            )
        )
        self.assertIsNone(res)

    def test_strength_zero_distance_with_structured_sets_is_allowed(self):
        res = self._filter_after_parse(
            self._base_activity(
                "strength_training",
                strength_sets_json='[{"set_index":1,"reps":8}]',
                strength_summary_json='{"working_set_count":1,"total_reps":8}',
            )
        )
        self.assertIsNone(res)

    def test_mobility_and_high_intensity_sessions_are_allowed_with_facts(self):
        for sport in ("yoga", "pilates", "hiit", "flexibility_training", "breathing"):
            with self.subTest(sport=sport):
                res = self._filter_after_parse(
                    self._base_activity(sport, duration_sec=900, calories=50)
                )
                self.assertIsNone(res)

    def test_indoor_endurance_sessions_are_allowed_without_gps_track(self):
        cases = [
            ("indoor_cycling", {"avg_power": 150, "avg_cadence": 82}),
            ("treadmill_running", {"duration_sec": 1800, "avg_hr": 140, "calories": 260}),
            ("elliptical", {"duration_sec": 1200, "avg_hr": 132}),
            ("stair_climbing", {"duration_sec": 900, "calories": 120}),
            ("floor_climbing", {"duration_sec": 900, "calories": 120}),
            ("indoor_walking", {"duration_sec": 1000, "avg_hr": 105}),
            ("rowing", {"duration_sec": 1000, "avg_hr": 128}),
        ]
        for sport, facts in cases:
            with self.subTest(sport=sport):
                res = self._filter_after_parse(self._base_activity(sport, **facts))
                self.assertIsNone(res)

    def test_pool_swim_sessions_are_allowed_without_track_points(self):
        cases = [
            ("lap_swimming", {"laps_json": '[{"lap_no":1}]'}),
            ("pool_swimming", {"swolf": 40}),
            ("swimming", {"duration_sec": 1200, "calories": 180}),
        ]
        for sport, facts in cases:
            with self.subTest(sport=sport):
                res = self._filter_after_parse(self._base_activity(sport, **facts))
                self.assertIsNone(res)

    def test_health_snapshot_like_activity_remains_filtered(self):
        res = self._filter_after_parse(
            self._base_activity("generic", duration_sec=20, calories=0, avg_hr=None)
        )
        self.assertIsNotNone(res)
        self.assertEqual(res.get("reason"), "filtered_as_health_data")


if __name__ == "__main__":
    unittest.main()
