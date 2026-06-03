"""
P0 修复验证：GPX 导入路径必须触发 region 补全 + 缓存预热
契约依据：§五 数据可信分层、§十一.2 审查门禁

运行方式：python -m pytest test_p0_gpx_region.py -v
"""

import sqlite3
import tempfile
import unittest
from unittest import mock
from datetime import datetime
from pathlib import Path

import main
import profile_backend


# ── helpers ──────────────────────────────────────────────────────

def _make_mock_conn(cache_rows=None):
    """构造 mock sqlite3.Connection，支持 geocode_cache 查询。"""
    mock_conn = mock.MagicMock(spec=sqlite3.Connection)
    mock_cursor = mock.MagicMock()
    mock_conn.__enter__ = mock.MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = mock.MagicMock(return_value=False)

    if cache_rows is not None:
        # _conn() 返回的 conn 上调用 execute(...).fetchone() 返回缓存行
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchone.return_value = mock_cursor
        # 配置 cursor 字段访问
        for k, v in cache_rows.items():
            setattr(mock_cursor, k, v)
        mock_cursor.__getitem__ = lambda self, k: cache_rows.get(k)
    if cache_rows is None:
        # 缓存未命中
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

    return mock_conn


def _make_gpx_data(lat=30.5, lon=104.0):
    """构造有效的 GPX 轨迹数据。"""
    return {
        "points": [
            {"lat": lat, "lon": lon, "alt": 500.0, "time": "2024-01-01T00:00:00Z"},
            {"lat": lat + 0.01, "lon": lon + 0.01, "alt": 510.0, "time": "2024-01-01T00:05:00Z"},
        ],
    }


# ── P0-1: _api_import_track 触发 region 调度 ──────────────────────

class TestP0ImportTrackRegionEnrichment(unittest.TestCase):
    """验证 P0-1 修复：GPX 主动导入后触发异步 region 补全。"""

    def setUp(self):
        self.api = main.Api()

    def test_success_triggers_region_enrichment(self):
        """GPX 导入成功 → _schedule_region_enrichment 被调用 1 次"""
        with mock.patch("profile_backend.ingest_activity_file") as mock_ingest, \
             mock.patch.object(self.api, "_schedule_region_enrichment") as mock_sched:
            mock_ingest.return_value = {"ok": True, "activity": {"id": 1}}
            result = self.api.import_track(file_path="/tmp/test.gpx")
            self.assertTrue(result["ok"])
            mock_sched.assert_called_once()
            mock_ingest.assert_called_once_with(
                mock.ANY, duplicate_action="", new_filename=None,
            )

    def test_duplicate_skips_enrichment(self):
        """重复导入不触发 Nominatim（避免配额浪费）"""
        with mock.patch("profile_backend.ingest_activity_file") as mock_ingest, \
             mock.patch.object(self.api, "_schedule_region_enrichment") as mock_sched:
            mock_ingest.return_value = {
                "ok": True, "duplicate": True, "score": 95,
            }
            self.api.import_track(file_path="/tmp/test.gpx")
            mock_sched.assert_not_called()

    def test_enrichment_failure_not_blocking(self):
        """调度补全失败不应阻塞主流程（P0-1 异常隔离）"""
        with mock.patch("profile_backend.ingest_activity_file") as mock_ingest, \
             mock.patch.object(self.api, "_schedule_region_enrichment",
                               side_effect=RuntimeError("nominatim down")):
            mock_ingest.return_value = {"ok": True, "activity": {"id": 1}}
            result = self.api.import_track(file_path="/tmp/test.gpx")
            self.assertTrue(result["ok"])

    def test_ingest_ok_false_skips_enrichment(self):
        """ingest 返回 ok=False 时不触发补全"""
        with mock.patch("profile_backend.ingest_activity_file") as mock_ingest, \
             mock.patch.object(self.api, "_schedule_region_enrichment") as mock_sched:
            mock_ingest.return_value = {"ok": False, "error": "parse failed"}
            result = self.api.import_track(file_path="/tmp/test.gpx")
            self.assertFalse(result["ok"])
            mock_sched.assert_not_called()

    def test_ingest_raises_skips_enrichment(self):
        """ingest 抛异常时不触发补全，正常返回 error"""
        with mock.patch("profile_backend.ingest_activity_file",
                         side_effect=ValueError("boom")), \
             mock.patch.object(self.api, "_schedule_region_enrichment") as mock_sched:
            result = self.api.import_track(file_path="/tmp/test.gpx")
            self.assertFalse(result["ok"])
            self.assertIn("boom", result["error"])
            mock_sched.assert_not_called()

    def test_non_dict_result_skips_enrichment(self):
        """防御：result 不是 dict 时不触发补全"""
        with mock.patch("profile_backend.ingest_activity_file") as mock_ingest, \
             mock.patch.object(self.api, "_schedule_region_enrichment") as mock_sched:
            mock_ingest.return_value = "weird-string"
            self.api.import_track(file_path="/tmp/test.gpx")
            mock_sched.assert_not_called()


# ── P0-2: ingest_activity_file 缓存预热 ───────────────────────────

class TestP0CachePrefetch(unittest.TestCase):
    """验证 P0-2 修复：geocode_cache 命中时同步写 region_*，失败不阻塞。"""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.src_path = Path(self.tmpdir.name) / "test.gpx"
        # 创建一个合法的 .gpx 文件（使 is_file() 返回 True）
        self.src_path.write_text(
            '<?xml version="1.0"?>'
            '<gpx><trk><trkseg>'
            '<trkpt lat="30.5" lon="104.0"><ele>500</ele><time>2024-01-01T00:00:00Z</time></trkpt>'
            '<trkpt lat="30.51" lon="104.01"><ele>510</ele><time>2024-01-01T00:05:00Z</time></trkpt>'
            '</trkseg></trk></gpx>'
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    # ── 缓存命中 ──────────────────────────────────────────────

    @mock.patch("track_backend.parse_track_file")
    @mock.patch("profile_backend._conn")
    @mock.patch("profile_backend._region_cache_key")
    @mock.patch("profile_backend.check_duplicate_activity")
    @mock.patch("profile_backend.copy_track_to_local")
    @mock.patch("profile_backend.save_activity")
    def test_cache_hit_updates_region_in_db(
        self, mock_save, mock_copy, mock_dup,
        mock_rk, mock_conn_func, mock_parse,
    ):
        """geocode_cache 命中 → UPDATE activities SET region_* = 'success'"""
        data = _make_gpx_data()
        mock_parse.return_value = data
        mock_save.return_value = 42
        mock_copy.return_value = str(self.src_path)
        mock_dup.return_value = {"is_duplicate": False}
        mock_rk.return_value = ("30.50,104.00", 30.5, 104.0)
        mock_conn_func.return_value = _make_mock_conn(
            {"city": "成都", "country": "中国", "display": "成都/中国"}
        )

        result = profile_backend.ingest_activity_file(str(self.src_path))
        self.assertTrue(result["ok"])
        self.assertIsInstance(result["activity"]["id"], int)

        # save_activity 被调用 1 次
        mock_save.assert_called_once()

        # geocode_cache 被查询
        execute_calls = [
            c[0][0] for c in mock_conn_func.return_value.execute.call_args_list
            if c[0]
        ]
        self.assertTrue(
            any("geocode_cache" in sql for sql in execute_calls),
            "未查询 geocode_cache 表"
        )
        # UPDATE activities 被执行（含 region_status = 'success'）
        self.assertTrue(
            any("UPDATE activities" in sql and "region_status" in sql
                for sql in execute_calls),
            "未执行 UPDATE activities SET region_* 语句"
        )

    # ── 缓存未命中 ────────────────────────────────────────────

    @mock.patch("track_backend.parse_track_file")
    @mock.patch("profile_backend._conn")
    @mock.patch("profile_backend._region_cache_key")
    @mock.patch("profile_backend.check_duplicate_activity")
    @mock.patch("profile_backend.copy_track_to_local")
    @mock.patch("profile_backend.save_activity")
    def test_cache_miss_does_not_update_region(
        self, mock_save, mock_copy, mock_dup,
        mock_rk, mock_conn_func, mock_parse,
    ):
        """geocode_cache 未命中 → 不写 region_status='success'"""
        data = _make_gpx_data()
        mock_parse.return_value = data
        mock_save.return_value = 42
        mock_copy.return_value = str(self.src_path)
        mock_dup.return_value = {"is_duplicate": False}
        mock_rk.return_value = ("30.50,104.00", 30.5, 104.0)
        mock_conn_func.return_value = _make_mock_conn(None)

        result = profile_backend.ingest_activity_file(str(self.src_path))
        self.assertTrue(result["ok"])
        mock_save.assert_called_once()

        execute_calls = [
            c[0][0] for c in mock_conn_func.return_value.execute.call_args_list
            if c[0]
        ]
        self.assertFalse(
            any("region_status = 'success'" in sql for sql in execute_calls),
            "缓存未命中时不应更新 region_status 为 success"
        )

    # ── 无 GPS ────────────────────────────────────────────────

    @mock.patch("track_backend.parse_track_file")
    @mock.patch("profile_backend._conn")
    @mock.patch("profile_backend.check_duplicate_activity")
    @mock.patch("profile_backend.copy_track_to_local")
    @mock.patch("profile_backend.save_activity")
    def test_no_gps_skips_prefetch(
        self, mock_save, mock_copy, mock_dup, mock_conn_func, mock_parse,
    ):
        """start_lat/start_lon 为 None → 跳过缓存预热，不查 geocode_cache"""
        data = {"points": []}  # 无 GPS
        mock_parse.return_value = data
        mock_save.return_value = 42
        mock_copy.return_value = str(self.src_path)
        mock_dup.return_value = {"is_duplicate": False}
        mock_conn_func.return_value = _make_mock_conn(None)

        result = profile_backend.ingest_activity_file(str(self.src_path))
        self.assertTrue(result["ok"])
        mock_save.assert_called_once()

        execute_calls = [
            c[0][0] for c in mock_conn_func.return_value.execute.call_args_list
            if c[0]
        ]
        geocode_queries = [sql for sql in execute_calls if "geocode_cache" in sql]
        self.assertEqual(
            len(geocode_queries), 0,
            f"无 GPS 时不应查询 geocode_cache，但实际查询了 {len(geocode_queries)} 次"
        )

    # ── 预热异常 ──────────────────────────────────────────────

    @mock.patch("track_backend.parse_track_file")
    @mock.patch("profile_backend._conn")
    @mock.patch("profile_backend._region_cache_key")
    @mock.patch("profile_backend.check_duplicate_activity")
    @mock.patch("profile_backend.copy_track_to_local")
    @mock.patch("profile_backend.save_activity")
    def test_prefetch_exception_not_blocking(
        self, mock_save, mock_copy, mock_dup,
        mock_rk, mock_conn_func, mock_parse,
    ):
        """_region_cache_key 抛异常 → save_activity 仍被调用，不抛异常"""
        data = _make_gpx_data()
        mock_parse.return_value = data
        mock_save.return_value = 42
        mock_copy.return_value = str(self.src_path)
        mock_dup.return_value = {"is_duplicate": False}
        mock_rk.side_effect = RuntimeError("db locked")
        mock_conn_func.return_value = _make_mock_conn(None)

        result = profile_backend.ingest_activity_file(str(self.src_path))
        self.assertTrue(result["ok"])
        mock_save.assert_called_once()

    # ── Duplicate 路径 ────────────────────────────────────────

    def test_duplicate_path_skips_save_and_prefetch(self):
        """查重命中且 action 不是 force/merge → 提前返回，不调 save_activity"""
        with mock.patch("track_backend.parse_track_file",
                         return_value=_make_gpx_data()) as mock_parse, \
             mock.patch("profile_backend.check_duplicate_activity",
                         return_value={"is_duplicate": True, "score": 95}) as mock_dup, \
             mock.patch("profile_backend.save_activity") as mock_save, \
             mock.patch("profile_backend.copy_track_to_local") as mock_copy:
            mock_copy.return_value = str(self.src_path)

            result = profile_backend.ingest_activity_file(str(self.src_path))
            self.assertTrue(result["ok"])
            self.assertTrue(result.get("duplicate"))
            self.assertEqual(result.get("score"), 95)
            mock_save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
