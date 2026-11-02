# -*- coding: utf-8 -*-
"""Block model: header fields + mined nonce, hashed via canonical JSON."""
import time

from .crypto_utils import hash_object
from .transaction import Transaction


class Block:
    """A block bundles transactions and links to the previous block's hash.

    The PoW input is the header dict; `nonce` is varied until the header
    hash meets the difficulty target.
    """

    def __init__(self, index: int, transactions: list, previous_hash: str,
                 timestamp: float = None, nonce: int = 0):
        self.index = index
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.transactions = list(transactions)
        self.previous_hash = previous_hash
        self.nonce = nonce

    def header_dict(self) -> dict:
        """Everything the block hash commits to (txs via their hashes)."""
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "tx_hashes": [tx.tx_hash() for tx in self.transactions],
        }

    def compute_hash(self) -> str:
        """SHA-256 over the canonical header — this is the block's identity."""
        return hash_object(self.header_dict())

    def to_dict(self) -> dict:
        return {
            **self.header_dict(),
            "hash": self.compute_hash(),
            "transactions": [tx.to_dict() for tx in self.transactions],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Block":
        txs = [Transaction.from_dict(t) for t in d["transactions"]]
        return cls(
            index=d["index"],
            transactions=txs,
            previous_hash=d["previous_hash"],
            timestamp=d.get("timestamp"),
            nonce=d.get("nonce", 0),
        )

    def __repr__(self) -> str:
        return (f"Block(index={self.index}, nonce={self.nonce}, "
                f"txs={len(self.transactions)}, hash={self.compute_hash()[:16]}...)")
