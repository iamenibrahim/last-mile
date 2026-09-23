import unittest

from api.ingest import load_cached_alert
from api.manifest import validate_manifest
from api.transform import transform_alert


class ManifestTests(unittest.TestCase):
    def test_manifest_validates_and_tampering_fails(self):
        result = transform_alert(load_cached_alert(), language="en")
        text = "\n".join(segment["output"] for segment in result["segments"])
        self.assertTrue(validate_manifest(result["manifest"], text)["valid"])
        self.assertFalse(validate_manifest(result["manifest"], text + " changed")["valid"])

    def test_signing_key_is_inside_the_signed_body(self):
        result = transform_alert(load_cached_alert(), language="en")
        manifest = result["manifest"]
        self.assertIn(manifest["signing"]["algorithm"], {"HMAC-SHA256", "RS256"})
        manifest["signing"]["algorithm"] = "none"
        self.assertFalse(validate_manifest(manifest)["signature_valid"])

    def test_demo_fixture_never_claims_tls_fetch(self):
        result = transform_alert(load_cached_alert(), language="en")
        self.assertEqual(result["manifest"]["source"]["transport"], "local demo fixture")
        self.assertIn("synthetic", result["manifest"]["trust_boundary"])
        self.assertIn("not an active alert", result["manifest"]["trust_boundary"])


if __name__ == "__main__":
    unittest.main()
