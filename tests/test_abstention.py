import unittest

from api.ingest import load_cached_alert
from api.transform import transform_alert


class AbstentionTests(unittest.TestCase):
    def test_clean_english_transformation_passes(self):
        result = transform_alert(load_cached_alert(), language="en")
        self.assertTrue(result["segments"])
        self.assertTrue(all(item["status"] == "translated_verified" for item in result["segments"]))

    def test_corrupted_entity_abstains_only_one_segment(self):
        result = transform_alert(load_cached_alert(), language="en", simulate_failure=True)
        abstained = [item for item in result["segments"] if item["status"] == "verbatim_abstained"]
        verified = [item for item in result["segments"] if item["status"] == "translated_verified"]
        self.assertEqual(len(abstained), 1)
        self.assertTrue(verified)
        self.assertEqual(abstained[0]["output"], abstained[0]["source"])
        self.assertEqual(abstained[0]["reason"], "entity_integrity")

    def test_empty_instruction_is_never_invented(self):
        alert = load_cached_alert()
        alert["properties"]["instruction"] = ""
        result = transform_alert(alert, language="en")
        self.assertFalse(result["instruction_present"])
        self.assertIn("No actions were inferred", result["instruction_notice"])
        self.assertFalse(any(item["section"] == "instruction" for item in result["segments"]))

    def test_cached_spanish_keeps_instruction_mapping(self):
        result = transform_alert(load_cached_alert(), language="es")
        instruction_segments = [item for item in result["segments"] if item["section"] == "instruction"]
        self.assertTrue(instruction_segments)
        self.assertTrue(all(item["status"] == "translated_verified" for item in instruction_segments))


if __name__ == "__main__":
    unittest.main()
