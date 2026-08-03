import json
import sqlite3
import unittest

import career_backend


def _create_schema(conn):
    conn.execute(
        """
        CREATE TABLE activities (
            id TEXT PRIMARY KEY,
            sport_type TEXT,
            sub_sport_type TEXT,
            start_time TEXT,
            distance_m REAL,
            dist_km REAL,
            duration_sec REAL,
            points_json TEXT,
            lengths_json TEXT,
            swim_water_scope TEXT,
            swim_pool_length_m REAL,
            swim_pool_length_unit TEXT,
            swim_pool_length_scope TEXT,
            swim_stroke_scope TEXT,
            swim_facts_quality_json TEXT,
            deleted_at TEXT,
            is_mock INTEGER
        )
        """
    )
    career_backend.ensure_career_schema(conn)


def _pool_lengths(values):
    return json.dumps(
        [
            {"index": index, "elapsed_sec": elapsed, "swim_stroke": "freestyle"}
            for index, elapsed in enumerate(values)
        ]
    )


def _open_water_stream(distance_m, elapsed_sec):
    return json.dumps(
        [
            {
                "distance_m": round(distance_m * index / 10, 3),
                "t_sec": round(elapsed_sec * index / 10, 3),
            }
            for index in range(11)
        ]
    )


def _timeline_nodes(conn):
    timeline = career_backend.get_career_timeline({"type": "record"}, conn)
    return [
        node
        for year in timeline["years"]
        for month in year["months"]
        for node in month["nodes"]
    ]


class CareerRecordSwimTimelineLifecycleTest(unittest.TestCase):
    def setUp(self):
        career_backend._clear_record_metric_series_cache()
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        _create_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def _insert_pool_activity(self, activity_id, date, lengths):
        self.conn.execute(
            """
            INSERT INTO activities (
                id, sport_type, sub_sport_type, start_time, duration_sec,
                lengths_json, swim_water_scope, swim_pool_length_m,
                swim_pool_length_unit, swim_pool_length_scope,
                swim_stroke_scope, swim_facts_quality_json, is_mock
            )
            VALUES (
                ?, 'swimming', 'lap_swimming', ?, ?, ?, 'pool_swimming',
                25, 'm', 'scm_25m', 'freestyle', '{}', 0
            )
            """,
            (
                activity_id,
                f"{date}T08:00:00Z",
                sum(lengths),
                _pool_lengths(lengths),
            ),
        )

    def _insert_open_water_activity(self, activity_id, date, distance_m, elapsed_sec):
        self.conn.execute(
            """
            INSERT INTO activities (
                id, sport_type, sub_sport_type, start_time, distance_m,
                dist_km, duration_sec, points_json, is_mock
            )
            VALUES (?, 'swimming', 'open_water', ?, ?, ?, ?, ?, 0)
            """,
            (
                activity_id,
                f"{date}T08:00:00Z",
                distance_m,
                distance_m / 1000.0,
                elapsed_sec,
                _open_water_stream(distance_m, elapsed_sec),
            ),
        )

    def test_pool_canonical_facts_drive_current_best_progression_and_promotion(self):
        self._insert_pool_activity("pool-base", "2026-07-01", [35, 35])
        self._insert_pool_activity("pool-breakthrough", "2026-07-02", [32, 32])
        self._insert_pool_activity("pool-best", "2026-07-03", [30, 30])

        rebuilt = career_backend.rebuild_career_record_metric_results(
            self.conn,
            sport="pool_swimming",
            record_keys=["pool_swim_50m"],
            dry_run=False,
        )
        self.assertEqual(rebuilt["summary"]["upserted"], 3)

        records = career_backend.get_career_records(
            {"sport": "pool_swimming", "record_key": "pool_swim_50m"},
            conn=self.conn,
        )
        self.assertEqual(records["records"][0]["activity_id"], "pool-best")

        nodes = [
            node
            for node in _timeline_nodes(self.conn)
            if node["record_key"] == "pool_swim_50m"
        ]
        self.assertIn(
            ("pool-breakthrough", "record_breaking", "刷新纪录：泳池 50m"),
            {(node["activity_id"], node["event_type"], node["title"]) for node in nodes},
        )
        self.assertIn(
            ("pool-best", "current_best", "最佳记录：泳池 50m"),
            {(node["activity_id"], node["event_type"], node["title"]) for node in nodes},
        )
        self.assertNotIn(
            ("pool-best", "record_breaking"),
            {(node["activity_id"], node["event_type"]) for node in nodes},
        )

        invalidated = career_backend.invalidate_career_record_metric_results_for_activity(
            self.conn,
            "pool-best",
            reason="delete_activities",
            dry_run=False,
        )
        self.assertEqual(invalidated["invalidated"], 1)
        promoted = career_backend.get_career_records(
            {"sport": "pool_swimming", "record_key": "pool_swim_50m"},
            conn=self.conn,
        )
        self.assertEqual(promoted["records"][0]["activity_id"], "pool-breakthrough")
        promoted_nodes = [
            node
            for node in _timeline_nodes(self.conn)
            if node["record_key"] == "pool_swim_50m"
        ]
        self.assertEqual(
            [(node["activity_id"], node["event_type"]) for node in promoted_nodes],
            [("pool-breakthrough", "current_best")],
        )

    def test_open_water_standard_distance_current_best_and_promotion_share_event_identity(self):
        self._insert_open_water_activity("open-base", "2026-07-04", 10000, 15000)
        self._insert_open_water_activity("open-breakthrough", "2026-07-05", 10000, 14400)
        self._insert_open_water_activity("open-best", "2026-07-06", 10000, 13800)

        rebuilt = career_backend.rebuild_career_record_metric_results(
            self.conn,
            sport="open_water_swimming",
            record_keys=["open_water_swim_10k"],
            dry_run=False,
        )
        self.assertEqual(rebuilt["summary"]["upserted"], 3)

        nodes = [
            node
            for node in _timeline_nodes(self.conn)
            if node["record_key"] == "open_water_swim_10k"
        ]
        self.assertIn(
            ("open-breakthrough", "record_breaking", "刷新纪录：公开水域 10K"),
            {(node["activity_id"], node["event_type"], node["title"]) for node in nodes},
        )
        self.assertIn(
            ("open-best", "current_best", "最佳记录：公开水域 10K"),
            {(node["activity_id"], node["event_type"], node["title"]) for node in nodes},
        )
        self.assertNotIn(
            ("open-best", "record_breaking"),
            {(node["activity_id"], node["event_type"]) for node in nodes},
        )

        career_backend.invalidate_career_record_metric_results_for_activity(
            self.conn,
            "open-best",
            reason="delete_activities",
            dry_run=False,
        )
        records = career_backend.get_career_records(
            {
                "sport": "open_water_swimming",
                "record_key": "open_water_swim_10k",
            },
            conn=self.conn,
        )
        self.assertEqual(records["records"][0]["activity_id"], "open-breakthrough")
        promoted_nodes = [
            node
            for node in _timeline_nodes(self.conn)
            if node["record_key"] == "open_water_swim_10k"
        ]
        self.assertEqual(
            [(node["activity_id"], node["event_type"]) for node in promoted_nodes],
            [("open-breakthrough", "current_best")],
        )

    def test_open_water_activity_total_current_best_replaces_same_state_breaking_card(self):
        self._insert_open_water_activity("open-short", "2026-07-07", 5000, 7200)
        self._insert_open_water_activity("open-long", "2026-07-08", 10000, 14400)

        career_backend.rebuild_career_record_metric_results(
            self.conn,
            sport="open_water_swimming",
            record_keys=[
                "open_water_longest_distance",
                "open_water_longest_elapsed_time",
            ],
            dry_run=False,
        )

        nodes = _timeline_nodes(self.conn)
        for record_key in (
            "open_water_longest_distance",
            "open_water_longest_elapsed_time",
        ):
            key_nodes = [node for node in nodes if node["record_key"] == record_key]
            self.assertEqual(
                [(node["activity_id"], node["event_type"]) for node in key_nodes],
                [("open-long", "current_best")],
            )
            self.assertEqual(key_nodes[0]["badge"], "最佳记录")


if __name__ == "__main__":
    unittest.main()
