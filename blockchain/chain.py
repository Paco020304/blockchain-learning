# -*- coding: utf-8 -*-
"""Blockchain: mempool, PoW mining, validation, longest-chain replacement."""
from .block import Block
from .crypto_utils import MINING_REWARD_SENDER
from .transaction import Transaction

MINING_REWARD_AMOUNT = 25.0
GENESIS_PREV_HASH = "0" * 64


class Blockchain:
    """A single node's view of the chain plus its pending transaction pool."""

    def __init__(self, difficulty: int = 4):
        self.difficulty = difficulty
        self.chain = []
        self.pending_transactions = []
        self._create_genesis_block()

    def _create_genesis_block(self) -> None:
        """Deterministic genesis (fixed timestamp) so every node agrees on it."""
        genesis = Block(index=0, transactions=[],
                        previous_hash=GENESIS_PREV_HASH, timestamp=0.0)
        self._proof_of_work(genesis)
        self.chain.append(genesis)

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    # ---------- proof of work ----------

    def _proof_of_work(self, block: Block) -> str:
        """Increment nonce until the header hash meets the difficulty target."""
        target = "0" * self.difficulty
        block.nonce = 0
        while not block.compute_hash().startswith(target):
            block.nonce += 1
        return block.compute_hash()

    def is_valid_pow(self, block: Block) -> bool:
        return block.compute_hash().startswith("0" * self.difficulty)

    # ---------- transactions / mempool ----------

    def submit_transaction(self, tx: Transaction) -> bool:
        """Accept a transaction into the mempool only if its signature verifies."""
        if not tx.has_valid_signature():
            return False
        self.pending_transactions.append(tx)
        return True

    def _remove_included_transactions(self, block: Block) -> None:
        included = {t.tx_hash() for t in block.transactions}
        self.pending_transactions = [
            t for t in self.pending_transactions if t.tx_hash() not in included
        ]

    # ---------- mining ----------

    def mine_pending_transactions(self, miner_address: str) -> Block:
        """Pack mempool + coinbase reward into a new block and mine it."""
        reward = Transaction(
            sender=MINING_REWARD_SENDER,
            recipient=miner_address,
            amount=MINING_REWARD_AMOUNT,
        )
        block = Block(
            index=len(self.chain),
            transactions=[reward] + self.pending_transactions,
            previous_hash=self.last_block.compute_hash(),
        )
        self._proof_of_work(block)
        self.chain.append(block)
        self._remove_included_transactions(block)
        return block

    # ---------- validation ----------

    def validate_block(self, block: Block, previous_block: Block) -> bool:
        """Check one block against its parent: linkage, index, PoW, tx signatures."""
        if block.index != previous_block.index + 1:
            return False
        if block.previous_hash != previous_block.compute_hash():
            return False
        if not self.is_valid_pow(block):
            return False
        return all(tx.has_valid_signature() for tx in block.transactions)

    def add_block(self, block: Block) -> bool:
        """Append a broadcast block only if it directly extends our tip."""
        if not self.validate_block(block, self.last_block):
            return False
        self.chain.append(block)
        self._remove_included_transactions(block)
        return True

    def validate_chain(self, chain: list = None) -> bool:
        """Validate a whole chain: genesis PoW plus every block's linkage."""
        chain = self.chain if chain is None else chain
        if not chain or not self.is_valid_pow(chain[0]):
            return False
        return all(
            self.validate_block(chain[i], chain[i - 1])
            for i in range(1, len(chain))
        )

    # ---------- consensus ----------

    def replace_chain(self, new_chain: list) -> bool:
        """Longest-chain rule: adopt a remote chain only if longer AND valid."""
        if len(new_chain) <= len(self.chain):
            return False
        if not self.validate_chain(new_chain):
            return False
        self.chain = list(new_chain)
        for block in self.chain:
            self._remove_included_transactions(block)
        return True

    # ---------- serialization ----------

    def to_dict(self) -> dict:
        return {
            "length": len(self.chain),
            "difficulty": self.difficulty,
            "chain": [b.to_dict() for b in self.chain],
        }

    @classmethod
    def chain_from_dicts(cls, chain_dicts: list) -> list:
        return [Block.from_dict(d) for d in chain_dicts]
