import unittest

from api.entities import entity_integrity, lock_entities, restore_entities


class EntityIntegrityTests(unittest.TestCase):
    def test_every_critical_entity_is_locked_and_restored_exactly(self):
        source = (
            "Norfolk residents: avoid VA-168 near Exit 12 until 8:00 PM EDT. "
            "Water may rise 3 feet. Call 757-555-0199 or visit https://www.weather.gov/."
        )
        locked = lock_entities(source, ["Norfolk"])
        kinds = {entity.kind for entity in locked.entities}
        self.assertTrue({"place", "road", "time", "measurement", "phone", "url"}.issubset(kinds))
        self.assertTrue(entity_integrity(locked.masked, locked.entities)["passed"])
        self.assertEqual(restore_entities(locked.masked, locked.entities), source)

    def test_drop_and_duplicate_are_detected(self):
        locked = lock_entities("Avoid VA-168 until 8:00 PM EDT.")
        dropped = locked.masked.replace(locked.entities[0].token, "", 1)
        duplicated = locked.masked + " " + locked.entities[0].token
        self.assertFalse(entity_integrity(dropped, locked.entities)["passed"])
        self.assertFalse(entity_integrity(duplicated, locked.entities)["passed"])

    def test_modal_may_is_not_mistaken_for_the_month(self):
        locked = lock_entities("Water may rise 3 feet near roads.")
        self.assertNotIn("[[E1]] rise", locked.masked)
        self.assertIn("may rise", locked.masked)


if __name__ == "__main__":
    unittest.main()
