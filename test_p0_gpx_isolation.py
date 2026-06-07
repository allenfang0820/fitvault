"""GPX 用后即抛契约测试。

§二 §八：验证 _assert_gpx_not_persisted 在所有写库入口拒绝 .gpx/.kml,
并验证 find_gpx_pollution 审计接口的 schema 正确性。
"""
import unittest

import profile_backend
from profile_backend import _assert_gpx_not_persisted, find_gpx_pollution


class TestGpxNotPersisted(unittest.TestCase):
    def test_blocks_gpx_filename(self):
        with self.assertRaises(ValueError) as ctx:
            _assert_gpx_not_persisted({"file_name": "track.gpx"})
        self.assertIn("GPX", str(ctx.exception))

    def test_blocks_gpx_file_path(self):
        with self.assertRaises(ValueError):
            _assert_gpx_not_persisted({"file_path": "/tmp/track.gpx"})

    def test_blocks_kml(self):
        with self.assertRaises(ValueError):
            _assert_gpx_not_persisted({"filename": "track.kml"})

    def test_blocks_case_insensitive(self):
        with self.assertRaises(ValueError):
            _assert_gpx_not_persisted({"file_name": "TRACK.GPX"})

    def test_allows_fit(self):
        # 不应抛异常
        _assert_gpx_not_persisted({"file_name": "activity.fit"})

    def test_allows_no_filename(self):
        # 没有文件名不应抛
        _assert_gpx_not_persisted({})

    def test_blocks_when_any_of_three_keys_gpx(self):
        # 三个键中任意一个 .gpx 都应拒绝
        with self.assertRaises(ValueError):
            _assert_gpx_not_persisted({"file_name": "x.fit", "filename": "y.gpx", "file_path": "z.fit"})


class TestFindGpxPollution(unittest.TestCase):
    def test_returns_expected_schema(self):
        res = find_gpx_pollution()
        self.assertIn("type_a_contradiction", res)
        self.assertIn("type_b_explicit_gpx", res)
        self.assertIn("total_count", res)

    def test_a_is_subset_of_b(self):
        res = find_gpx_pollution()
        a_ids = {r["id"] for r in res["type_a_contradiction"]}
        b_ids = {r["id"] for r in res["type_b_explicit_gpx"]}
        self.assertTrue(a_ids.issubset(b_ids), "A 类应⊆B 类")

    def test_total_count_matches_b(self):
        res = find_gpx_pollution()
        self.assertEqual(res["total_count"], len(res["type_b_explicit_gpx"]))


if __name__ == "__main__":
    unittest.main()
