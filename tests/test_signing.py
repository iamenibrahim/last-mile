from types import SimpleNamespace

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from api.signing import verify_with_public_jwk
from grounded.providers.azure_providers import KeyVaultSigner


def _vault_signer_with(private_key):
    """A KeyVaultSigner whose vault is replaced by a local RSA key, so the
    public-key export can be checked without Azure."""
    numbers = private_key.public_key().public_numbers()
    signer = KeyVaultSigner.__new__(KeyVaultSigner)
    signer.key_id = "https://example.vault.azure.net/keys/manifest-signing/1"
    signer._jwk = SimpleNamespace(
        n=numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big"),
        e=numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big"),
    )
    return signer


def test_anyone_can_verify_an_rs256_signature_with_the_published_key():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = _vault_signer_with(private_key).public_jwk()
    assert jwk["kty"] == "RSA" and jwk["alg"] == "RS256"

    payload = b'{"packet":"DR-4831-VA"}'
    # Key Vault's RS256 is PKCS#1 v1.5 over SHA-256, the same as this.
    signature = private_key.sign(payload, padding.PKCS1v15(), hashes.SHA256()).hex()

    assert verify_with_public_jwk(jwk, payload, signature)
    assert not verify_with_public_jwk(jwk, payload + b" ", signature)


def test_key_vault_signer_verifies_with_public_key_without_remote_call():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private_key.public_key().public_numbers()
    signer = object.__new__(KeyVaultSigner)
    signer._jwk = SimpleNamespace(
        n=numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big"),
        e=numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big"),
    )
    payload = b"signed disaster action packet"
    signature = private_key.sign(payload, padding.PKCS1v15(), hashes.SHA256()).hex()

    assert signer.verify(payload, signature)
    assert not signer.verify(payload + b"!", signature)
