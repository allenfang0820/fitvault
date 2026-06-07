"""任务 1 — 圈速数据真实化回归测试

契约:fit-arch-contrac §2.1 — UI 字段必须能追溯至 FIT SDK
验证:
  1. _read_lap_data 从 FIT 消息中正确提取 lap 字段
  2. _normalize_laps 过滤掉 0/0 假数据
  3. _build_real_laps_from_row 优先返回 DB 数据,fallback 到 _build_lap_rows
  4. activities 表 schema 已新增 laps_json 列
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional
from unittest import mock

import fit_engine
from metrics_resolver import MetricsResolver


class FakeField:
    def __init__(self, name: str, value: Any) -> None:
        self.name = name
        self.value = value


class FakeMessage:
    def __init__(self, **kwargs: Any) -> None:
        self._data = dict(kwargs)
        self.fields = [FakeField(k, v) for k, v in self._data.items()]

    def get_value(self, key: str) -> Any:
        return self._data.get(key)


class FakeFitFile:
    """模拟 FitFile,提供 lap_mesgs 数据。"""

    def __init__(self, _path: str, check_crc: bool = True) -> None:
        self.lap_messages = [
            FakeMessage(
                index=0,
                start_time="2026-05-20T11:30:00Z",
                total_distance=1000.0,
                total_timer_time=300.0,
                avg_heart_rate=145,
                max_heart_rate=158,
                avg_cadence=178,
                avg_power=245,
                total_calories=80,
            ),
            FakeMessage(
                index=1,
                start_time="2026-05-20T11:35:00Z",
                total_distance=1000.0,
                total_timer_time=305.0,
                avg_heart_rate=148,
                max_heart_rate=160,
                avg_cadence=176,
                avg_power=250,
                total_calories=82,
            ),
        ]

    def get_messages(self, kind: str):
        if kind == "lap":
            return iter(self.lap_messages)
        return iter([])


class TestFitEngineLapData(unittest.TestCase):
    """步骤 1.1: _read_lap_data 提取验证"""

    def test_read_lap_data_extracts_all_fields(self):
        with mock.patch.object(fit_engine.FitFile, "__init__", lambda self, *a, **kw: None), \
             mock.patch.object(fit_engine.FitFile, "get_messages", lambda self, k: FakeFitFile("").get_messages(k)):
            fake = FakeFitFile("")
            laps = fit_engine.FITCoreEngine._read_lap_data(fake)
        self.assertEqual(len(laps), 2)
        first = laps[0]
        self.assertEqual(first["total_distance"], 1000.0)
        self.assertEqual(first["total_timer_time"], 300.0)
        self.assertEqual(first["avg_heart_rate"], 145)
        self.assertEqual(first["avg_cadence"], 178)
        self.assertEqual(first["avg_power"], 245)
        self.assertIsNotNone(first["lap_start_time"])

    def test_read_lap_data_empty_file(self):
        with mock.patch.object(fit_engine.FitFile, "__init__", lambda self, *a, **kw: None), \
             mock.patch.object(fit_engine.FitFile, "get_messages", lambda self, k: iter([])):
            fake = FakeFitFile("")
            laps = fit_engine.FITCoreEngine._read_lap_data(fake)
        self.assertEqual(laps, [])


class TestNormalizeLaps(unittest.TestCase):
    """步骤 1.2: 复用 _normalize_laps 过滤无效数据"""

    def test_normalize_filters_zero_distance_and_time(self):
        raw = [
            {"total_distance": 1000.0, "total_timer_time": 300.0, "avg_heart_rate": 145, "avg_power": 245, "avg_cadence": 178},
            {"total_distance": 0, "total_timer_time": 0, "avg_heart_rate": 0, "avg_power": 0, "avg_cadence": 0},
            {"total_distance": 800.0, "total_timer_time": 240.0, "avg_heart_rate": 150, "avg_power": 250, "avg_cadence": 180},
        ]
        normalized = MetricsResolver._normalize_laps(raw)
        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0]["distance_m"], 1000.0)
        self.assertEqual(normalized[0]["elapsed_sec"], 300.0)
        self.assertEqual(normalized[1]["distance_m"], 800.0)

    def test_normalize_empty_input(self):
        self.assertEqual(MetricsResolver._normalize_laps([]), [])


class TestBuildRealLapsFromRow(unittest.TestCase):
    """步骤 1.5: 详情页优先读取真实数据"""

    def test_returns_real_laps_when_laps_json_present(self):
        row = {
            "laps_json": json.dumps([
                {"lap_index": 0, "distance_m": 1000.0, "elapsed_sec": 300.0, "avg_hr": 145, "avg_power": 245, "avg_cadence": 178},
                {"lap_index": 1, "distance_m": 1000.0, "elapsed_sec": 305.0, "avg_hr": 148, "avg_power": 250, "avg_cadence": 176},
            ])
        }
        from main import _build_real_laps_from_row
        result = _build_real_laps_from_row(row, dist_km=2.0, duration_sec=605, avg_hr=146, base_power=240)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["lap_no"], 1)
        self.assertEqual(result[0]["distance_km"], 1.0)
        self.assertEqual(result[0]["pace_sec"], 300)
        self.assertEqual(result[0]["hr"], 145)
        self.assertEqual(result[0]["cadence"], 178)
        self.assertEqual(result[0]["power_w"], 245)
        self.assertEqual(result[1]["lap_no"], 2)

    def test_returns_empty_when_laps_json_missing(self):
        from main import _build_real_laps_from_row
        result = _build_real_laps_from_row({}, dist_km=5.0, duration_sec=1500, avg_hr=150, base_power=240)
        self.assertEqual(result, [])

    def test_returns_empty_when_laps_json_invalid_json(self):
        from main import _build_real_laps_from_row
        result = _build_real_laps_from_row({"laps_json": "{invalid"}, dist_km=5.0, duration_sec=1500, avg_hr=150, base_power=240)
        self.assertEqual(result, [])

    def test_skips_laps_with_zero_distance_and_time(self):
        row = {
            "laps_json": json.dumps([
                {"lap_index": 0, "distance_m": 1000.0, "elapsed_sec": 300.0, "avg_hr": 145, "avg_power": 245, "avg_cadence": 178},
                {"lap_index": 1, "distance_m": 0, "elapsed_sec": 0, "avg_hr": 0, "avg_power": 0, "avg_cadence": 0},
            ])
        }
        from main import _build_real_laps_from_row
        result = _build_real_laps_from_row(row, dist_km=1.0, duration_sec=300, avg_hr=145, base_power=245)
        self.assertEqual(len(result), 1)


class TestSchemaLapsColumn(unittest.TestCase):
    """步骤 1.3: 验证 activities 表已有 laps_json 列"""

    def test_laps_json_column_exists(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        try:
            import profile_backend
            conn = sqlite3.connect(db_path)
            try:
                profile_backend._ensure_schema_initialized(conn)
                cur = conn.execute("PRAGMA table_info(activities)")
                cols = {row[1] for row in cur.fetchall()}
                self.assertIn("laps_json", cols, "laps_json 列未成功加入 activities 表")
            finally:
                conn.close()
        finally:
            Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
