from unittest import mock

import main


def test_import_track_delegates_gpx_to_preview_parser_without_persistence(tmp_path):
    gpx_path = tmp_path / "preview.gpx"
    gpx_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="unit-test">
  <trk><name>preview</name><trkseg>
    <trkpt lat="30.6700" lon="104.0600"><ele>500</ele><time>2026-07-11T00:00:00Z</time></trkpt>
  </trkseg></trk>
</gpx>
""",
        encoding="utf-8",
    )

    preview_payload = {"ok": True, "points": [{"lat": 30.67, "lon": 104.06}], "source": "preview"}
    api = main.Api.__new__(main.Api)

    with mock.patch("profile_backend.parse_route_for_preview", return_value=preview_payload) as parser:
        result = api.import_track(file_path=str(gpx_path), duplicate_action="replace")

    assert result == preview_payload
    parser.assert_called_once_with(str(gpx_path), resolve_region=False)


def test_import_track_rejects_non_route_files_without_calling_preview_parser(tmp_path):
    fit_path = tmp_path / "activity.fit"
    fit_path.write_bytes(b"not-a-route-preview-file")
    api = main.Api.__new__(main.Api)

    with mock.patch("profile_backend.parse_route_for_preview") as parser:
        result = api.import_track(file_path=str(fit_path), duplicate_action="replace")

    assert result["ok"] is False
    assert ".gpx" in result["error"]
    parser.assert_not_called()
