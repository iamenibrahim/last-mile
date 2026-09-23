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



def test_azure_maps_is_tried_before_the_census_geocoder(monkeypatch):
    import dataclasses
    from types import SimpleNamespace

    import grounded.geo
    from api import geo

    monkeypatch.setattr(geo, "settings", dataclasses.replace(geo.settings, azure_maps_key="test-key"))
    monkeypatch.setattr(
        grounded.geo,
        "_azure_geocode",
        lambda address: SimpleNamespace(lat=36.88, lon=-81.76, matched_address="Saltville, VA 24370"),
    )
    found = geo.geocode("742 Evergreen Terrace, Abingdon, VA")
    assert found["provider"] == "Azure Maps"
    assert (found["point"].longitude, found["point"].latitude) == (-81.76, 36.88)
