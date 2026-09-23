import unittest

from api.fraud import scan_message
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


if __name__ == "__main__":
    unittest.main()

