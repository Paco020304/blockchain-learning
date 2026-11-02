# -*- coding: utf-8 -*-
"""Transaction model with RSA signature support."""
import time

from .crypto_utils import (
    MINING_REWARD_SENDER,
    canonical_json,
    hash_object,
    public_key_from_pem,
    sign_payload,
    verify_payload_signature,
)


class Transaction:
    """A transfer of `amount` from `sender` to `recipient`.

    `sender` is the PEM-encoded public key of the originator (its identity),
    or MINING_REWARD_SENDER for unsigned coinbase reward transactions.
    `signature` is a hex RSA signature over the canonical payload.
    """

    def __init__(self, sender: str, recipient: str, amount: float,
                 timestamp: float = None, signature: str = None):
        self.sender = sender
        self.recipient = recipient
        self.amount = float(amount)
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.signature = signature

    def payload_dict(self) -> dict:
        """Signed fields only — the signature itself is never part of it."""
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": self.amount,
            "timestamp": self.timestamp,
        }

    def payload_bytes(self) -> bytes:
        return canonical_json(self.payload_dict()).encode("utf-8")

    def sign(self, private_key) -> None:
        """Sign the payload with the sender's RSA private key."""
        self.signature = sign_payload(private_key, self.payload_bytes())

    def has_valid_signature(self) -> bool:
        """Coinbase txs are exempt; others must verify against sender pubkey."""
        if self.sender == MINING_REWARD_SENDER:
            return True
        if not self.signature:
            return False
        try:
            public_key = public_key_from_pem(self.sender)
        except Exception:
            return False
        return verify_payload_signature(
            public_key, self.signature, self.payload_bytes()
        )

    def tx_hash(self) -> str:
        """Content hash of the full transaction (signature included)."""
        return hash_object(self.to_dict())

    def to_dict(self) -> dict:
        d = self.payload_dict()
        d["signature"] = self.signature
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Transaction":
        return cls(
            sender=d["sender"],
            recipient=d["recipient"],
            amount=d["amount"],
            timestamp=d.get("timestamp"),
            signature=d.get("signature"),
        )

    def __repr__(self) -> str:
        return (f"Transaction(sender=...{self.sender[-15:].strip()}, "
                f"recipient={self.recipient!r}, amount={self.amount})")
