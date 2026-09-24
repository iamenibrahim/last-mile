import unittest

from api.fraud import scan_message
from api.geo import geocode
from api.navigator import navigate


class NavigatorTests(unittest.TestCase):
    def test_lost_id_path_surfaces_alternatives_without_collecting_id(self):
        result = navigate(
            {
                "location": "23510",
                "urgency": "safe_now",
                "needs": ["documents", "housing"],
                "circumstances": ["no_id", "displaced"],
                "housing": None,
            }
        )
        ids = [item["id"] for item in result["recommendations"]]
        self.assertIn("id-replacement", ids)
        self.assertTrue(result["handoff"]["recommended"])
        self.assertFalse(result["privacy"]["stored"])
        self.assertIn("Social Security number", result["privacy"]["not_requested"])

    def test_fraud_checker_never_calls_message_safe(self):
        risky = scan_message("Pay a fee by gift card now and send your SSN at https://help.example.com")
        self.assertEqual(risky["risk"], "high")
        clean = scan_message("Apply at https://www.disasterassistance.gov/")
        self.assertEqual(clean["risk"], "no_obvious_red_flags")
        self.assertIn("not proof", clean["notice"])

    def test_sensitive_ambiguous_and_high_impact_cases_get_human_handoff(self):
        cases = [
            ("sensitive", ["housing"], ["unsafe_shelter"]),
            ("ambiguous", ["housing"], ["complex_case"]),
            ("high_impact", ["legal"], ["appeal_or_denied"]),
        ]
        for expected, needs, circumstances in cases:
            with self.subTest(level=expected):
                result = navigate(
                    {
                        "location": "24370",
                        "urgency": "safe_now",
                        "needs": needs,
                        "circumstances": circumstances,
                    }
                )
                self.assertTrue(result["handoff"]["recommended"])
                self.assertEqual(result["handoff"]["level"], expected)
                self.assertNotIn(circumstances[0], result["handoff"]["summary"]["circumstances"])
                self.assertTrue(result["handoff"]["summary"]["private_review_requested"])

    def test_fraud_concern_adds_official_human_reporting_path(self):
        result = navigate(
            {
                "location": "24370",
                "urgency": "safe_now",
                "needs": ["money"],
                "circumstances": ["fraud_concern"],
            }
        )
        self.assertEqual(result["handoff"]["level"], "sensitive")
        self.assertIn("866-720-5721", [item["value"] for item in result["handoff"]["contacts"]])

    def test_device_coordinates_are_used_directly_but_not_copied_to_handoff(self):
        point = geocode("36.8508, -76.2859")
        self.assertEqual(point["provider"], "browser-geolocation")
        self.assertAlmostEqual(point["point"].latitude, 36.8508)
        self.assertAlmostEqual(point["point"].longitude, -76.2859)
        result = navigate(
            {
                "location": "36.8508, -76.2859",
                "urgency": "safe_now",
                "needs": ["housing"],
                "circumstances": [],
            }
        )
        self.assertNotIn("36.8508", result["handoff"]["summary"]["location_shared"])


if __name__ == "__main__":
    unittest.main()
