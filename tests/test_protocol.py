import unittest

from api.protocol import build_action_packet, continuity_store, next_question, verify_action_packet


class LastMileProtocolTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "location": "24370",
            "jurisdiction": "Smyth County",
            "needs": ["home_repair", "housing", "documents"],
            "circumstances": ["displaced", "no_id"],
            "context_reviewed": True,
        }

    def test_ambiguous_zip_asks_only_for_county(self):
        result = next_question({"location": "24370"})
        self.assertFalse(result["complete"])
        self.assertEqual(result["question"]["id"], "jurisdiction")
        self.assertIn("Smyth County", result["question"]["choices"])

    def test_one_packet_compiles_all_channels_with_locked_facts(self):
        result = build_action_packet(self.profile)
        self.assertEqual(result["status"], "complete")
        packet = result["packet"]
        self.assertEqual(set(packet["channels"]), {"web", "sms", "voice", "offline"})
        for channel in packet["channels"].values():
            self.assertIn("DR-4831-VA", channel["locked_facts"])
            self.assertIn("2024-12-02", channel["locked_facts"])
            self.assertIn("Smyth County", channel["locked_facts"])
        self.assertLessEqual(packet["channels"]["sms"]["characters"], 320)
        self.assertTrue(verify_action_packet(packet)["valid"])

    def test_channel_tampering_breaks_proof(self):
        packet = build_action_packet(self.profile)["packet"]
        packet["channels"]["sms"]["text"] = packet["channels"]["sms"]["text"].replace(
            "2024", "2025"
        )
        self.assertFalse(verify_action_packet(packet)["valid"])

    def test_rewritten_channel_with_recomputed_hash_still_fails(self):
        from api.protocol import _hash

        packet = build_action_packet(self.profile)["packet"]
        packet["channels"]["sms"]["text"] = "Call 555-0100 to claim your payment."
        packet["proof"]["channels_sha256"] = _hash(packet["channels"])
        result = verify_action_packet(packet)
        self.assertTrue(result["channels_valid"])
        self.assertFalse(result["signature_valid"])
        self.assertFalse(result["valid"])

    def test_packet_records_its_signing_key(self):
        proof = build_action_packet(self.profile)["packet"]["proof"]
        self.assertIn(proof["algorithm"], {"HMAC-SHA256", "RS256"})
        self.assertTrue(proof["key_id"])

    def test_anonymous_code_resumes_minimal_state(self):
        packet = build_action_packet(self.profile)["packet"]
        resumed = continuity_store.load(packet["continuity"]["code"])
        self.assertIsNotNone(resumed)
        blob = str(resumed)
        self.assertNotIn("Social Security", blob)
        self.assertEqual(resumed["location_input"], "24370")
        self.assertIn("street address", resumed["continuity"]["excludes"])


if __name__ == "__main__":
    unittest.main()
