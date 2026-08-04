from __future__ import annotations

import unittest

from scripts.release_version import normalize_release_version


class ReleaseVersionTests(unittest.TestCase):
    def test_accepts_plain_or_v_prefixed_semver(self) -> None:
        self.assertEqual(normalize_release_version("v2.0.0"), "2.0.0")
        self.assertEqual(normalize_release_version("2.10.3"), "2.10.3")

    def test_rejects_non_release_tags(self) -> None:
        for value in ("", "v2.0", "v2.0.0-rc.1", "release-2.0.0"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_release_version(value)
