import json
import unittest
from pathlib import Path

import career_backend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORLD_GEOJSON_PATH = PROJECT_ROOT / "assets" / "career_footprint_world.geo.json"
CHINA_GEOJSON_PATH = PROJECT_ROOT / "assets" / "career_footprint_china.geo.json"
JAPAN_GEOJSON_PATH = PROJECT_ROOT / "assets" / "career_footprint_japan.geo.json"
US_MAP_SCRIPT_PATH = PROJECT_ROOT / "assets" / "career_footprint_us.js"
MANIFEST_PATH = PROJECT_ROOT / "assets" / "career_footprint_maps_manifest.json"
RUNTIME_MAPS_PATH = PROJECT_ROOT / "assets" / "career_footprint_maps.js"


class TestCareerFootprintMapAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world_raw = WORLD_GEOJSON_PATH.read_text(encoding="utf-8")
        cls.china_raw = CHINA_GEOJSON_PATH.read_text(encoding="utf-8")
        cls.japan_raw = JAPAN_GEOJSON_PATH.read_text(encoding="utf-8")
        cls.us_script_raw = US_MAP_SCRIPT_PATH.read_text(encoding="utf-8")
        cls.manifest_raw = MANIFEST_PATH.read_text(encoding="utf-8")
        cls.runtime_raw = RUNTIME_MAPS_PATH.read_text(encoding="utf-8")
        cls.world = json.loads(cls.world_raw)
        cls.china = json.loads(cls.china_raw)
        cls.japan = json.loads(cls.japan_raw)
        cls.us = json.loads(cls.us_script_raw.split("window.FITVAULT_CAREER_FOOTPRINT_MAPS.us=", 1)[1].rstrip(";\n"))
        cls.manifest = json.loads(cls.manifest_raw)

    def test_assets_are_local_geojson_and_runtime_script_is_data_only(self):
        for path in (WORLD_GEOJSON_PATH, CHINA_GEOJSON_PATH, JAPAN_GEOJSON_PATH, US_MAP_SCRIPT_PATH, MANIFEST_PATH, RUNTIME_MAPS_PATH):
            self.assertTrue(path.exists(), str(path))

        self.assertEqual(self.world["type"], "FeatureCollection")
        self.assertEqual(self.china["type"], "FeatureCollection")
        self.assertEqual(self.japan["type"], "FeatureCollection")
        self.assertEqual(self.us["type"], "FeatureCollection")
        self.assertEqual(self.manifest["runtime"], "echarts-register-map")
        self.assertIn("window.FITVAULT_CAREER_FOOTPRINT_MAPS", self.runtime_raw)
        self.assertNotIn("FITVAULT_CAREER_FOOTPRINT_MAPS.us", self.runtime_raw)
        self.assertIn("career_footprint_world.geo.json", self.manifest_raw)
        self.assertIn("career_footprint_china.geo.json", self.manifest_raw)
        self.assertIn("career_footprint_japan.geo.json", self.manifest_raw)
        self.assertIn("career_footprint_us.js", self.manifest_raw)

    def test_assets_do_not_embed_online_map_services(self):
        combined = "\n".join([self.world_raw, self.china_raw, self.japan_raw, self.us_script_raw, self.manifest_raw, self.runtime_raw])
        for token in ("http://", "https://", "cdn", "openstreetmap", "tianditu", "mapbox", "leaflet", "tileLayer"):
            self.assertNotIn(token, combined.lower())

    def test_china_geojson_covers_backend_region_keys_including_taiwan(self):
        asset_keys = {feature["properties"]["region_key"] for feature in self.china["features"]}
        backend_keys = {spec[0] for spec in career_backend.CAREER_FOOTPRINT_CHINA_REGION_SPECS}

        self.assertTrue(backend_keys <= asset_keys)
        self.assertIn("CN-TW", asset_keys)

    def test_world_geojson_covers_backend_country_keys(self):
        asset_keys = {feature["properties"]["key"] for feature in self.world["features"]}
        backend_country_keys = {spec[0] for spec in career_backend.CAREER_FOOTPRINT_COUNTRY_SPECS.values()}

        self.assertTrue(backend_country_keys <= asset_keys)
        self.assertGreaterEqual(len(asset_keys), 170)

    def test_world_geojson_covers_popular_marathon_and_southeast_asia_countries(self):
        asset_keys = {feature["properties"]["key"] for feature in self.world["features"]}
        expected = {
            "US", "GB", "DE", "JP", "FR", "AU", "IT", "ES", "NL", "GR", "CA", "ZA",
            "SG", "TH", "VN", "MY", "ID", "PH", "KH", "LA", "MM", "BN",
        }

        self.assertTrue(expected <= asset_keys)

    def test_japan_geojson_covers_prefecture_drilldown_keys(self):
        asset_keys = {feature["properties"]["region_key"] for feature in self.japan["features"]}
        backend_keys = {spec[0] for spec in career_backend.CAREER_FOOTPRINT_JAPAN_REGION_SPECS}

        self.assertEqual(len(asset_keys), 47)
        self.assertTrue(backend_keys <= asset_keys)
        self.assertIn("JP-13", asset_keys)
        self.assertIn("JP-47", asset_keys)

    def test_us_map_script_covers_state_drilldown_keys(self):
        asset_keys = {feature["properties"]["region_key"] for feature in self.us["features"]}
        backend_keys = {spec[0] for spec in career_backend.CAREER_FOOTPRINT_US_REGION_SPECS}

        self.assertEqual(len(asset_keys), 51)
        self.assertTrue(backend_keys <= asset_keys)
        self.assertIn("US-CA", asset_keys)
        self.assertIn("US-NY", asset_keys)
        self.assertIn("US-DC", asset_keys)

    def test_features_have_stable_keys_names_and_geometries(self):
        for feature in self.world["features"]:
            props = feature["properties"]
            self.assertRegex(props["key"], r"^[A-Z0-9_]{2,}$")
            self.assertIsInstance(props["name"], str)
            self.assertTrue(props["name"])
            self.assertIn(feature["geometry"]["type"], {"Polygon", "MultiPolygon"})

        for feature in self.china["features"]:
            props = feature["properties"]
            self.assertRegex(props["region_key"], r"^CN-[A-Z]{2}$")
            self.assertEqual(props["region_key"], props["key"])
            self.assertIsInstance(props["name"], str)
            self.assertTrue(props["name"])
            self.assertIn(feature["geometry"]["type"], {"Polygon", "MultiPolygon"})

        for feature in self.japan["features"]:
            props = feature["properties"]
            self.assertRegex(props["region_key"], r"^JP-\d{2}$")
            self.assertEqual(props["region_key"], props["key"])
            self.assertIsInstance(props["name"], str)
            self.assertTrue(props["name"])
            self.assertEqual(feature["geometry"]["type"], "MultiPolygon")

        for feature in self.us["features"]:
            props = feature["properties"]
            self.assertRegex(props["region_key"], r"^US-[A-Z]{2}$")
            self.assertEqual(props["region_key"], props["key"])
            self.assertIsInstance(props["name"], str)
            self.assertTrue(props["name"])
            self.assertIn(feature["geometry"]["type"], {"Polygon", "MultiPolygon"})

    def test_manifest_declares_cn_jp_and_us_drilldowns(self):
        self.assertEqual(self.manifest["supported_drilldowns"], {"CN": "china", "JP": "japan", "US": "us"})
        self.assertEqual(self.manifest["maps"]["world"]["key_property"], "key")
        self.assertEqual(self.manifest["maps"]["china"]["key_property"], "region_key")
        self.assertEqual(self.manifest["maps"]["japan"]["key_property"], "region_key")
        self.assertEqual(self.manifest["maps"]["us"]["key_property"], "region_key")
        self.assertEqual(self.manifest["maps"]["us"]["script"], "assets/career_footprint_us.js")


if __name__ == "__main__":
    unittest.main()
