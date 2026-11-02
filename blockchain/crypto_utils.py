# -*- coding: utf-8 -*-
"""Shared crypto helpers: canonical JSON, SHA-256, RSA sign/verify."""
import hashlib
import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

MINING_REWARD_SENDER = "MINING_REWARD"

_PSS_PADDING = padding.PSS(
    mgf=padding.MGF1(hashes.SHA256()),
    salt_length=padding.PSS.MAX_LENGTH,
)


def canonical_json(obj) -> str:
    """Serialize an object deterministically (sorted keys, compact separators)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(data: bytes) -> str:
    """Return the SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def hash_object(obj) -> str:
    """SHA-256 hex digest of an object's canonical JSON encoding."""
    return sha256_hex(canonical_json(obj).encode("utf-8"))


def generate_rsa_keypair():
    """Generate an RSA-2048 key pair, returns (private_key, public_key)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def public_key_to_pem(public_key) -> str:
    """Encode an RSA public key as a PEM string (used as the sender identity)."""
    return public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def public_key_from_pem(pem: str):
    """Load an RSA public key from its PEM string."""
    return serialization.load_pem_public_key(pem.encode("utf-8"))


def sign_payload(private_key, payload: bytes) -> str:
    """Sign raw bytes with an RSA private key, returns the signature as hex."""
    return private_key.sign(payload, _PSS_PADDING, hashes.SHA256()).hex()


def verify_payload_signature(public_key, signature_hex: str, payload: bytes) -> bool:
    """Verify a hex RSA signature over raw bytes; False on any failure."""
    try:
        public_key.verify(
            bytes.fromhex(signature_hex), payload, _PSS_PADDING, hashes.SHA256()
        )
        return True
    except Exception:
        return False
