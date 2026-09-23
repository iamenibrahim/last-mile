import unittest

from api.geo import Point, classify_position
from api.ingest import load_cached_alert


class GeographyTests(unittest.TestCase):
    def test_inside_and_outside_use_geometry(self):
        geometry = load_cached_alert()["geometry"]
        self.assertEqual(classify_position(Point(-76.2859, 36.8508), geometry)["status"], "inside")
        outside = classify_position(Point(-77.4360, 37.5407), geometry)
        self.assertEqual(outside["status"], "outside")
        self.assertGreater(outside["distance_km"], 10)


if __name__ == "__main__":
    unittest.main()

