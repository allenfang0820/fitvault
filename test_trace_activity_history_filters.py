"""§任务 6:历史轨迹抽屉过滤链路端到端测试

覆盖范围:
- profile_backend.get_activity_list_filtered 的 time_filter / location_filter 行为
- profile_backend.get_activity_location_options 的地区聚合 / 排除 / 排序行为
- main.Api.get_trace_activity_history 的端到端集成
- 地区选项 / 时间筛选 / 类型筛选的组合 + 边界
- SQL 参数绑定安全性
"""
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import main
import profile_backend


class TestTraceActivityHistoryFilters(unittest.TestCase):
    """§任务 6 全部 8 个场景 + 边界测试。"""

    def setUp(self):
        # 隔离:使用临时数据库,避免污染主 DB
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        self.original_db_path = profile_backend.DB_PATH
        self.original_schema = profile_backend._SCHEMA_READY_FOR
        self.original_main_schema = main._ACTIVITY_SYNC_SCHEMA_READY_FOR
        self.original_tracks_dir = main.TRACKS_DIR

        profile_backend.DB_PATH = self.temp_dir / "user_profile.db"
        profile_backend.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        profile_backend._SCHEMA_READY_FOR = None
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        main.TRACKS_DIR = str(self.temp_dir / "tracks")
        Path(main.TRACKS_DIR).mkdir(parents=True, exist_ok=True)

        # 触发 Api 初始化(创建 schema)
        self.api = main.Api()

        # 强制触发 schema 初始化(profile_backend._conn() 第一次调用时建表)
        _bootstrap = profile_backend._conn()
        _bootstrap.close()

        # 直接打开 conn 注入测试数据
        self.conn = sqlite3.connect(str(profile_backend.DB_PATH))
        self.conn.row_factory = sqlite3.Row
        self._seed_activities()

    def tearDown(self):
        self.conn.close()
        profile_backend.DB_PATH = self.original_db_path
        profile_backend._SCHEMA_READY_FOR = self.original_schema
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = self.original_main_schema
        main.TRACKS_DIR = self.original_tracks_dir
        self.temp_dir_obj.cleanup()

    def _seed_activities(self):
        """注入结构化测试数据:
        - 成都市/中国: 50 条
        - 北京市/中国: 20 条
        - 大阪市/日本: 5 条
        - 上海市/中国 (region_city): 3 条
        - 待补全 (region_status=pending, region为空): 2 条
        - 室内运动 (region_status=none): 1 条
        - 未知地点 (region_status=failed): 1 条
        共 82 条,跨 30 天 + 上年 + 今年。
        """
        rows = []
        # 成都市/中国: 50 条,跨 60 天,含 sport_type 混合
        for i in range(50):
            year = 2025 if i < 20 else 2026
            month = 1 + (i % 12)
            day = 1 + (i % 27)
            sport = "running" if i % 2 == 0 else "hiking"
            rows.append((
                f"chengdu_{i}.fit", sport, "unknown",
                f"{year}-{month:02d}-{day:02d}T08:00:00Z",
                30.67, 104.06, "成都市", "成都市", "中国", "成都市/中国", "ok",
                10.0, 3600, 150, 170, 620, "[]", "[]", "/tmp/foo.fit", 100.0,
            ))

        # 北京市/中国: 20 条
        for i in range(20):
            year = 2025 if i < 8 else 2026
            rows.append((
                f"beijing_{i}.fit", "running", "unknown",
                f"{year}-{1 + (i % 12):02d}-{1 + (i % 27):02d}T08:00:00Z",
                39.90, 116.40, "北京市", "北京市", "中国", "北京市/中国", "ok",
                8.0, 3000, 145, 165, 500, "[]", "[]", "/tmp/foo.fit", 80.0,
            ))

        # 大阪市/日本: 5 条
        for i in range(5):
            rows.append((
                f"osaka_{i}.fit", "running", "unknown",
                f"2026-{1 + i:02d}-15T08:00:00Z",
                34.69, 135.50, "大阪市", "大阪市", "日本", "大阪市/日本", "ok",
                5.0, 2400, 140, 160, 400, "[]", "[]", "/tmp/foo.fit", 50.0,
            ))

        # 上海市/中国: 仅 region_city,无 region_display/region — 验证优先级回落
        for i in range(3):
            rows.append((
                f"shanghai_{i}.fit", "running", "unknown",
                f"2026-0{i + 1}-15T08:00:00Z",
                31.23, 121.47, None, "上海市", "中国", None, "ok",
                6.0, 2700, 142, 162, 450, "[]", "[]", "/tmp/foo.fit", 60.0,
            ))

        # 待补全: 2 条
        for i in range(2):
            rows.append((
                f"pending_{i}.fit", "running", "unknown",
                f"2026-05-{1 + i:02d}T08:00:00Z",
                30.0, 120.0, None, None, None, None, "pending",
                5.0, 1800, 130, 150, 300, "[]", "[]", "/tmp/foo.fit", 30.0,
            ))

        # 室内运动: 1 条
        rows.append((
            "indoor_0.fit", "running", "unknown", "2026-05-10T08:00:00Z",
            30.0, 120.0, None, None, None, None, "none",
            3.0, 1500, 125, 145, 250, "[]", "[]", "/tmp/foo.fit", 0.0,
        ))

        # 未知地点: 1 条
        rows.append((
            "unknown_0.fit", "running", "unknown", "2026-05-12T08:00:00Z",
            30.0, 120.0, None, None, None, None, "failed",
            4.0, 1700, 128, 148, 280, "[]", "[]", "/tmp/foo.fit", 20.0,
        ))

        for r in rows:
            self.conn.execute(
                """
                INSERT INTO activities (
                    file_name, sport_type, sub_sport_type, start_time,
                    start_lat, start_lon, region, region_city, region_country,
                    region_display, region_status,
                    distance, duration, avg_hr, max_hr, calories,
                    track_json, points_json, file_path, gain_m
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                r,
            )
        self.conn.commit()

    # ===================================================================
    # 场景 1: 50 条同地区,page_size=30,total 应为 50(不是 30)
    # ===================================================================
    def test_filtered_total_uses_count_with_same_where(self):
        """场景 1: 50 条成都 + page_size=30,location_filter=成都市/中国 → total=50(不是 30)"""
        rows, total = profile_backend.get_activity_list_filtered(
            offset=0, limit=30, sport_filter="all", gps_only=True,
            location_filter="成都市/中国",
        )
        self.assertEqual(total, 50, "total 应反映筛选后总数(50),不是分页容量(30)")
        self.assertEqual(len(rows), 30, "当前页仍为 30 条")

    # ===================================================================
    # 场景 2: 地区选项应包含不在第一页的地区
    # ===================================================================
    def test_location_options_include_regions_beyond_first_page(self):
        """场景 2: page_size=30,北京市活动 20 条在第一页,成都市 50 条溢出;
        location_options 必须包含 成都市/中国(不在第一页的城市)。
        """
        options = profile_backend.get_activity_location_options(
            sport_filter="all", gps_only=True,
        )
        labels = [o["value"] for o in options]
        # 必须包含 4 个真实地区
        self.assertIn("成都市/中国", labels, "成都市必须出现(50 条溢出第一页)")
        self.assertIn("北京市/中国", labels)
        self.assertIn("大阪市/日本", labels)
        # 上海市 — 通过 region_city 回落,应能进选项
        # 5 个 GPS 类型区(待补全/室内/未知/失败应被排除)
        # 计数:成都/北京/大阪 + 上海市(回落) = 4 个
        self.assertGreaterEqual(len(options), 4)

    # ===================================================================
    # 场景 3: 地区筛选后分页仍正确
    # ===================================================================
    def test_location_filter_pagination_remains_correct(self):
        """场景 3: 50 条成都 → page 1 = 30 条,page 2 = 20 条,total = 50。"""
        page1, total1 = profile_backend.get_activity_list_filtered(
            offset=0, limit=30, sport_filter="all", gps_only=True,
            location_filter="成都市/中国",
        )
        page2, total2 = profile_backend.get_activity_list_filtered(
            offset=30, limit=30, sport_filter="all", gps_only=True,
            location_filter="成都市/中国",
        )
        self.assertEqual(total1, 50)
        self.assertEqual(total2, 50)
        self.assertEqual(len(page1), 30)
        self.assertEqual(len(page2), 20)
        # 两页 id 不重叠
        page1_ids = {r["id"] for r in page1}
        page2_ids = {r["id"] for r in page2}
        self.assertEqual(len(page1_ids & page2_ids), 0, "page1 / page2 活动 id 必须不重叠")

    # ===================================================================
    # 场景 4: 时间 + 地区组合
    # ===================================================================
    def test_time_and_location_filter_combination(self):
        """场景 4: time_filter=this_year + location_filter=北京市/中国 → 仅 2026 年北京活动"""
        rows, total = profile_backend.get_activity_list_filtered(
            offset=0, limit=30, sport_filter="all", gps_only=True,
            time_filter="this_year", location_filter="北京市/中国",
        )
        # 北京市 20 条,其中 8 条是 2025,12 条是 2026
        self.assertEqual(total, 12, "this_year 应仅含 2026 年的 12 条")
        for r in rows:
            self.assertEqual(r["region_display"], "北京市/中国")
            self.assertIn("2026", r["start_time"], "所有记录 start_time 含 2026")

    # ===================================================================
    # 场景 5: 类型 + 地区组合
    # ===================================================================
    def test_sport_and_location_filter_combination(self):
        """场景 5: sport_filter=running + location_filter=成都市/中国 → 仅成都 running 活动"""
        rows, total = profile_backend.get_activity_list_filtered(
            offset=0, limit=30, sport_filter="running", gps_only=True,
            location_filter="成都市/中国",
        )
        # 50 条成都中,running 25 条(偶数下标)
        self.assertEqual(total, 25, "成都市 running 活动数应为 25")
        for r in rows:
            self.assertEqual(r["region_display"], "成都市/中国")
            self.assertIn(r["sport_type"], ("running",))

    # ===================================================================
    # 场景 6: location_filter="all" 保持原行为
    # ===================================================================
    def test_location_filter_all_preserves_original_behavior(self):
        """场景 6: location_filter='all' 应等价于不传(向后兼容)"""
        rows_default, total_default = profile_backend.get_activity_list_filtered(
            offset=0, limit=30, sport_filter="all", gps_only=True,
        )
        rows_all, total_all = profile_backend.get_activity_list_filtered(
            offset=0, limit=30, sport_filter="all", gps_only=True,
            location_filter="all",
        )
        self.assertEqual(total_default, total_all, "location_filter='all' 必须等价于不传")
        self.assertEqual(len(rows_default), len(rows_all))

    # ===================================================================
    # 场景 7: 空地区、待补全、室内运动不进入地区选项
    # ===================================================================
    def test_location_options_excludes_invalid_regions(self):
        """场景 7: 待补全(2) / 室内运动(1) / 未知地点(1) 不应进入 locations"""
        options = profile_backend.get_activity_location_options(
            sport_filter="all", gps_only=True,
        )
        labels = {o["value"] for o in options}
        # 排除项
        for excluded in ("待补全", "室内运动", "未知地点"):
            self.assertNotIn(excluded, labels, f"{excluded} 不应进地区选项")
        # 真实地区必须存在
        self.assertIn("成都市/中国", labels)
        self.assertIn("北京市/中国", labels)
        self.assertIn("大阪市/日本", labels)

    # ===================================================================
    # 场景 8: SQL 参数安全 — 地区名含 /、中文、空格、特殊字符
    # ===================================================================
    def test_sql_parameter_safety_with_special_characters(self):
        """场景 8: 地区名含特殊字符时参数绑定安全,不应触发 SQL 注入"""
        # 注入测试字符串
        injection_payloads = [
            "' OR 1=1 --",
            "成都市'; DROP TABLE activities; --",
            "a/b/c",
            "  北京市  ",  # 含前后空格
            "Osaka/日本",   # 含 / + 日文
        ]
        for payload in injection_payloads:
            with self.subTest(payload=payload):
                # 不抛异常即视为安全(参数绑定生效,SQL 不被污染)
                rows, total = profile_backend.get_activity_list_filtered(
                    offset=0, limit=10, sport_filter="all", gps_only=True,
                    location_filter=payload,
                )
                # 无匹配 → 0(因 payload 不是真实地区)
                self.assertEqual(total, 0, f"注入 payload '{payload}' 应被参数绑定阻断")
                self.assertEqual(len(rows), 0)

        # 注入后,数据库表应仍存在且可正常查询
        rows, total = profile_backend.get_activity_list_filtered(
            offset=0, limit=5, sport_filter="all", gps_only=True,
        )
        self.assertGreater(total, 0, "注入后数据库应未受破坏")


class TestTraceActivityHistoryApi(unittest.TestCase):
    """§任务 6:端到端 API 测试(get_trace_activity_history 完整链路)"""

    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        self.original_db_path = profile_backend.DB_PATH
        self.original_schema = profile_backend._SCHEMA_READY_FOR
        self.original_main_schema = main._ACTIVITY_SYNC_SCHEMA_READY_FOR
        self.original_tracks_dir = main.TRACKS_DIR

        profile_backend.DB_PATH = self.temp_dir / "user_profile.db"
        profile_backend.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        profile_backend._SCHEMA_READY_FOR = None
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = None
        main.TRACKS_DIR = str(self.temp_dir / "tracks")
        Path(main.TRACKS_DIR).mkdir(parents=True, exist_ok=True)

        self.api = main.Api()
        # 强制触发 schema 初始化
        _bootstrap = profile_backend._conn()
        _bootstrap.close()
        # 注入 5 条北京 + 1 条上海
        self._seed_activities()

    def tearDown(self):
        profile_backend.DB_PATH = self.original_db_path
        profile_backend._SCHEMA_READY_FOR = self.original_schema
        main._ACTIVITY_SYNC_SCHEMA_READY_FOR = self.original_main_schema
        main.TRACKS_DIR = self.original_tracks_dir
        self.temp_dir_obj.cleanup()

    def _seed_activities(self):
        conn = sqlite3.connect(str(profile_backend.DB_PATH))
        # 触发 schema(_conn 第一次调用会建表)
        for i in range(5):
            conn.execute(
                """INSERT INTO activities (
                    file_name, sport_type, sub_sport_type, start_time,
                    start_lat, start_lon, region, region_city, region_country,
                    region_display, region_status,
                    distance, duration, track_json, points_json, file_path
                ) VALUES (?, 'running', 'unknown', '2026-05-15T08:00:00Z',
                    39.90, 116.40, '北京市', '北京市', '中国', '北京市/中国', 'ok',
                    8.0, 3000, '[]', '[]', '/tmp/foo.fit')""",
                (f"bj_{i}.fit",),
            )
        conn.execute(
            """INSERT INTO activities (
                file_name, sport_type, sub_sport_type, start_time,
                start_lat, start_lon, region, region_city, region_country,
                region_display, region_status,
                distance, duration, track_json, points_json, file_path
            ) VALUES ('sh_0.fit', 'running', 'unknown', '2026-05-20T08:00:00Z',
                31.23, 121.47, '上海市', '上海市', '中国', '上海市/中国', 'ok',
                6.0, 2700, '[]', '[]', '/tmp/foo.fit')""",
        )
        conn.commit()
        conn.close()

    def test_api_returns_locations_field(self):
        """API 返回必须包含 locations 字段,结构 {value, label, count}"""
        res = self.api.get_trace_activity_history(page=1, page_size=10)
        self.assertTrue(res.get("ok"))
        self.assertIn("locations", res, "API 返回必须含 locations 字段")
        self.assertIsInstance(res["locations"], list)
        for loc in res["locations"]:
            self.assertIn("value", loc)
            self.assertIn("label", loc)
            self.assertIn("count", loc)
            self.assertIsInstance(loc["count"], int)

    def test_api_locations_independent_of_time_filter(self):
        """locations 字段必须不受 time_filter 影响(选址下拉是静态属性)"""
        res_default = self.api.get_trace_activity_history(
            page=1, page_size=10, time_filter="all"
        )
        res_30d = self.api.get_trace_activity_history(
            page=1, page_size=10, time_filter="30d"
        )
        res_90d = self.api.get_trace_activity_history(
            page=1, page_size=10, time_filter="90d"
        )
        self.assertEqual(
            res_default["locations"], res_30d["locations"],
            "30d 不应改变地区选项"
        )
        self.assertEqual(
            res_default["locations"], res_90d["locations"],
            "90d 不应改变地区选项"
        )

    def test_api_locations_linked_to_sport_filter(self):
        """locations 字段必须与 sport_filter 联动(不同运动有不同地区集合)"""
        res_all = self.api.get_trace_activity_history(
            page=1, page_size=10, sport_filter="all"
        )
        res_running = self.api.get_trace_activity_history(
            page=1, page_size=10, sport_filter="running"
        )
        res_hiking = self.api.get_trace_activity_history(
            page=1, page_size=10, sport_filter="hiking"
        )
        # running 用户有北京/上海;hiking 用户无数据
        labels_all = {l["value"] for l in res_all["locations"]}
        labels_running = {l["value"] for l in res_running["locations"]}
        labels_hiking = {l["value"] for l in res_hiking["locations"]}
        self.assertIn("北京市/中国", labels_all)
        self.assertIn("北京市/中国", labels_running)
        self.assertEqual(labels_hiking, set(), "hiking 用户无活动,地区选项应空")

    def test_api_total_reflects_filter(self):
        """total 字段必须是筛选后总数,不是 page_size"""
        res = self.api.get_trace_activity_history(
            page=1, page_size=10, location_filter="北京市/中国"
        )
        self.assertEqual(res["total"], 5, "北京 5 条活动")
        self.assertEqual(len(res["records"]), 5)
        self.assertEqual(res["total_pages"], 1)

    def test_api_pagination_works_with_filter(self):
        """地区筛选后分页仍正确"""
        res_p1 = self.api.get_trace_activity_history(
            page=1, page_size=2, location_filter="北京市/中国"
        )
        res_p2 = self.api.get_trace_activity_history(
            page=2, page_size=2, location_filter="北京市/中国"
        )
        res_p3 = self.api.get_trace_activity_history(
            page=3, page_size=2, location_filter="北京市/中国"
        )
        self.assertEqual(res_p1["total"], 5)
        self.assertEqual(res_p1["total_pages"], 3)
        self.assertEqual(len(res_p1["records"]), 2)
        self.assertEqual(len(res_p2["records"]), 2)
        self.assertEqual(len(res_p3["records"]), 1)

    def test_api_compound_filters(self):
        """sport + time + location 三联组合生效"""
        res = self.api.get_trace_activity_history(
            page=1, page_size=10,
            sport_filter="running",
            time_filter="this_year",
            location_filter="北京市/中国",
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["total"], 5, "5 条 2026 年北京 running 活动")
        for rec in res["records"]:
            self.assertIn("2026", rec.get("start_time", ""))

    def test_api_preserves_activity_types_field(self):
        """activity_types 字段保持原行为(独立于 time/location filter)"""
        res = self.api.get_trace_activity_history(
            page=1, page_size=10, time_filter="30d", location_filter="北京市/中国"
        )
        self.assertIn("activity_types", res)
        self.assertIn("running", res["activity_types"])
        # 不受 location_filter 影响
        res_no_loc = self.api.get_trace_activity_history(page=1, page_size=10)
        self.assertEqual(res["activity_types"], res_no_loc["activity_types"])


if __name__ == "__main__":
    unittest.main()
