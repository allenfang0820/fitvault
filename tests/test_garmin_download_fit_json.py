import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "skills" / "garmin-stats" / "scripts" / "download_fit.py"


def load_download_fit_module():
    module_name = "garmin_download_fit_for_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def fit_zip(payload=b"fit-bytes"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("activity.fit", payload)
    return buf.getvalue()


def empty_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", b"no fit")
    return buf.getvalue()


class FakeClient:
    def __init__(self):
        self.activities = []
        self.downloads = {}
        self.details = {}
        self.requested_ranges = []

    def get_activities_by_date(self, start_date, end_date, activity_type=None):
        self.requested_ranges.append((start_date, end_date, activity_type))
        return list(self.activities)

    def download_activity(self, activity_id, dl_fmt=None):
        value = self.downloads.get(int(activity_id), fit_zip())
        if isinstance(value, Exception):
            raise value
        return value

    def connectapi(self, endpoint):
        activity_id = int(str(endpoint).rstrip("/").split("/")[-1])
        return self.details.get(activity_id, {"activityName": f"Activity {activity_id}"})


class TestGarminDownloadFitJson(unittest.TestCase):
    def setUp(self):
        self.mod = load_download_fit_module()
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir_obj.name)
        self.client = FakeClient()
        self.ctx = self.mod.RuntimeContext(
            client=self.client,
            garminconnect=SimpleNamespace(
                Garmin=SimpleNamespace(
                    ActivityDownloadFormat=SimpleNamespace(ORIGINAL="original")
                )
            ),
            output_dir=str(self.output_dir),
            region="cn",
        )

    def tearDown(self):
        self.temp_dir_obj.cleanup()

    def test_json_date_range_outputs_summary_without_stdout_logs(self):
        self.client.activities = [
            {"activityId": 101, "activityName": "Morning Run"},
            {"activityId": 102, "activityName": "Evening Ride"},
        ]
        (self.output_dir / "Evening Ride_102.fit").write_bytes(b"old")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(self.mod, "create_runtime_context", return_value=self.ctx), \
             redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.mod.main([
                "--from", "2026-05-01",
                "--to", "2026-05-31",
                "--output-dir", str(self.output_dir),
                "--json",
            ])

        self.assertEqual(code, 0)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(summary["mode"], "date_range")
        self.assertEqual(summary["start_date"], "2026-05-01")
        self.assertEqual(summary["end_date"], "2026-05-31")
        self.assertEqual(summary["searched"], 2)
        self.assertEqual(summary["downloaded"], 1)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(len(summary["files"]), 1)
        self.assertIn("Morning Run_101.fit", summary["files"][0])
        self.assertNotIn("📊", stdout.getvalue())
        self.assertIn("找到 2 个活动", stderr.getvalue())

    def test_single_activity_id_json_output(self):
        summary = self.mod.download_activity_ids(self.ctx, ["301"], json_mode=True)

        self.assertTrue(summary["ok"], summary)
        self.assertEqual(summary["mode"], "activity_ids")
        self.assertEqual(summary["searched"], 1)
        self.assertEqual(summary["downloaded"], 1)
        self.assertEqual((self.output_dir / "Activity 301_301.fit").read_bytes(), b"fit-bytes")

    def test_download_failure_enters_errors(self):
        self.client.downloads[401] = RuntimeError("network down")

        summary = self.mod.download_activity_ids(self.ctx, ["401"], json_mode=True)

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["errors"][0]["activity_id"], 401)
        self.assertIn("network down", summary["errors"][0]["message"])

    def test_zip_without_fit_enters_failed(self):
        self.client.downloads[501] = empty_zip()

        summary = self.mod.download_activity_ids(self.ctx, ["501"], json_mode=True)

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["failed"], 1)
        self.assertIn("ZIP 内无 FIT 文件", summary["errors"][0]["message"])

    def test_existing_fit_enters_skipped(self):
        (self.output_dir / "Existing_601.fit").write_bytes(b"old")

        summary = self.mod.download_activity_ids(self.ctx, ["601"], json_mode=True)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["downloaded"], 0)

    def test_json_flag_is_not_treated_as_activity_id(self):
        args = self.mod.parse_args(["123", "--json"])

        self.assertTrue(args.json)
        self.assertEqual(args.activity_ids, ["123"])

    def test_non_json_mode_keeps_human_output_path(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            summary = self.mod.download_activity_ids(self.ctx, ["701"], json_mode=False)

        self.assertTrue(summary["ok"])
        self.assertIn("全部下载完成", stdout.getvalue())

    def test_region_and_output_dir_are_parsed(self):
        args = self.mod.parse_args([
            "--from", "2026-01-01",
            "--to", "2026-01-02",
            "--region", "global",
            "--output-dir", str(self.output_dir),
            "--json",
        ])

        self.assertEqual(args.region, "global")
        self.assertEqual(args.output_dir, str(self.output_dir))
        self.assertTrue(args.json)

    def test_date_range_query_failure_returns_json_error_summary(self):
        self.client.get_activities_by_date = mock.Mock(side_effect=RuntimeError("query failed"))

        summary = self.mod.download_by_date_range(
            self.ctx,
            "2026-05-01",
            "2026-05-31",
            json_mode=True,
        )

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["failed"], 1)
        self.assertIn("query failed", summary["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
