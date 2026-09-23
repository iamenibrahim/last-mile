from __future__ import annotations

from grounded.providers.base import get_registry


def _signer():
    return get_registry().signer


def sign(payload: bytes) -> dict:
    """Sign with Azure Key Vault (RS256) when configured, else the local HMAC dev key."""
    signer = _signer()
    return {"signature": signer.sign(payload), "key_id": signer.key_id, "algorithm": signer.algorithm}


def verify(payload: bytes, signature: str) -> bool:
    try:
        return bool(signature) and _signer().verify(payload, signature)
    except Exception:
        return False


def describe() -> dict:
    signer = _signer()
    public = signer.public_jwk()
    return {
        "algorithm": signer.algorithm,
        "key_id": signer.key_id,
        "public_jwk": public,
        "publicly_verifiable": public is not None,
        "note": (
            "RS256 key held in Azure Key Vault. The private key never leaves the vault; "
            "verify any manifest or packet with this public key."
            if public
            else "Local HMAC dev key: symmetric, so only this server can verify. "
            "Set AZURE_KEYVAULT_URL and AZURE_KEYVAULT_KEY_NAME for the Key Vault signer."
        ),
    }


def verify_with_public_jwk(jwk: dict, payload: bytes, signature: str) -> bool:
    """What an outside verifier does: RS256 check with only the published public key."""
    import base64

    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    def as_int(value: str) -> int:
        return int.from_bytes(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)), "big")

    public_key = rsa.RSAPublicNumbers(as_int(jwk["e"]), as_int(jwk["n"])).public_key()
    try:
        public_key.verify(bytes.fromhex(signature), payload, padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, ValueError):
        return False
