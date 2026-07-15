from __future__ import annotations

import json
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestFatigueReviewRealActivityReplay(unittest.TestCase):
    """FR-Core-11: real local activity replay smoke gate.

    The default gate samples one real activity per sport family from the local
    user DB. Set FULL_FATIGUE_REPLAY=1 to run every non-deleted local activity.
    Historical trend DB queries are mocked here because time-window/baseline
    semantics have dedicated tests; this gate focuses on snapshot invariants
    over real activity shapes without writing user data.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import profile_backend

        cls.db_path = Path(profile_backend.DB_PATH)
        if not cls.db_path.exists():
            raise unittest.SkipTest("local activity DB is not available")

    def _load_rows(self) -> list[dict]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(activities)").fetchall()}
            if not cols:
                self.skipTest("activities table is not available")
            where = "deleted_at IS NULL" if "deleted_at" in cols else "1=1"
            rows = [dict(r) for r in conn.execute(f"SELECT * FROM activities WHERE {where} ORDER BY id")]
        finally:
            conn.close()
        if not rows:
            self.skipTest("no real activities available for replay")
        if os.environ.get("FULL_FATIGUE_REPLAY") == "1":
            return rows

        # One representative row per observed sport, capped to keep the normal
        # gate fast while still covering special routing families.
        seen: dict[str, dict] = {}
        for row in rows:
            sport = str(row.get("sport_type") or "unknown")
            seen.setdefault(sport, row)
        priority = [
            "running",
            "cycling",
            "road_cycling",
            "e_biking",
            "walking",
            "hiking",
            "mountaineering",
            "swimming",
            "training",
            "strength_training",
            "stair_climbing",
            "cardio",
            "stand_up_paddleboarding",
        ]
        selected = [seen.pop(sport) for sport in priority if sport in seen]
        selected.extend(seen.values())
        return selected[:16]

    def _api(self):
        from main import Api

        api = Api.__new__(Api)
        api._fetch_efficiency_trend = MagicMock(
            return_value={"level": "flat", "compared_count": 0, "baseline_ratio": None}
        )
        api._fetch_durability_trend = MagicMock(
            return_value={
                "level": "flat",
                "compared_count": 0,
                "baseline_ratio": None,
                "basis": "speed_tail_head_ratio",
                "version": "fr_core_10_canonical_curve_v1",
                "source_quality": "smoke_mock",
            }
        )
        api._fetch_cadence_stability_trend = MagicMock(
            return_value={
                "level": "flat",
                "compared_count": 0,
                "baseline_cv": None,
                "basis": "cadence_cv",
                "version": "fr_core_10_canonical_curve_v1",
                "source_quality": "smoke_mock",
            }
        )
        api._fetch_training_load_trend = MagicMock(
            return_value={"level": "flat", "compared_count": 0, "baseline_load": None}
        )
        api._fetch_load_ratio_7d_42d = MagicMock(
            return_value={"ratio": None, "level": "unknown", "acute_7d": None, "chronic_42d": None}
        )
        return api

    def test_real_activity_replay_snapshot_invariants(self):
        from metrics_registry import get_review_mode

        api = self._api()
        rows = self._load_rows()
        self.assertGreaterEqual(len(rows), 1)

        for row in rows:
            with self.subTest(activity_id=row.get("id"), sport=row.get("sport_type")):
                snapshot = api._build_fatigue_review_snapshot(row)
                encoded = json.dumps(snapshot, ensure_ascii=False)
                for forbidden in ("shadow_diff", "shadow_diff_json", '"records"', '"points"'):
                    self.assertNotIn(forbidden, encoded)

                sport_type = row.get("sport_type")
                self.assertEqual(snapshot.get("review_mode"), get_review_mode(sport_type))
                self.assertIsInstance(snapshot.get("capabilities"), dict)

                curves = snapshot.get("curves") or {}
                axis_len = len(curves.get("distance") or [])
                for key, curve in curves.items():
                    if key == "total_distance_m" or not isinstance(curve, list) or not curve:
                        continue
                    self.assertEqual(len(curve), axis_len, key)

                metrics = snapshot.get("metrics") or {}
                for metric_key, metric in metrics.items():
                    if not isinstance(metric, dict):
                        continue
                    confidence = str(metric.get("confidence") or "").lower()
                    status = str(metric.get("status") or "").lower()
                    trend = metric.get("trend")
                    if isinstance(trend, dict) and (
                        confidence == "unavailable" or status in {"unavailable", "not_applicable"}
                    ):
                        self.assertIsNone(trend.get("delta_pct"), metric_key)
                        self.assertIsNone(trend.get("is_improving"), metric_key)

                if snapshot.get("review_mode") != "cycling":
                    self.assertNotEqual((metrics.get("durability") or {}).get("basis"), "power_retention")
