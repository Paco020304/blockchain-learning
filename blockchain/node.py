# -*- coding: utf-8 -*-
"""HTTP blockchain node built on the stdlib http.server.

Endpoints:
  GET  /chain         -> full chain (for sync)
  GET  /mempool       -> pending transactions
  POST /peers         -> {"peer": "host:port"} register + return known peers
  POST /transactions  -> {"transaction": {...}, "relay": bool} verify + gossip
  POST /blocks        -> {"block": {...}} append if it extends our tip, else sync
  POST /mine          -> {"miner": "..."} mine mempool into a block + broadcast
  POST /sync          -> pull peers' chains, adopt the longest valid one

Run a node:  python -m blockchain.node --port 5001 [--peer host:port ...]
"""
import argparse
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .block import Block
from .chain import Blockchain
from .transaction import Transaction

HTTP_TIMEOUT = 5


def post_json(url: str, payload: dict, timeout: int = HTTP_TIMEOUT):
    """POST a JSON body; returns parsed response dict or None on failure."""
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def get_json(url: str, timeout: int = HTTP_TIMEOUT):
    """GET a JSON resource; returns parsed body or None on failure."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


class BlockchainNode:
    """Owns a Blockchain, a peer set, and an HTTP server exposing them."""

    def __init__(self, host: str, port: int, difficulty: int = 4):
        self.host = host
        self.port = port
        self.blockchain = Blockchain(difficulty=difficulty)
        self.peers = set()  # peer addresses as "host:port"
        self.httpd = ThreadingHTTPServer((host, port), _NodeRequestHandler)
        self.httpd.node = self

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    def start(self) -> threading.Thread:
        """Serve HTTP in a background thread."""
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        return thread

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    # ---------- peer management ----------

    def register_peer(self, address: str) -> None:
        if address != self.address:
            self.peers.add(address)

    def connect_to_peer(self, address: str) -> bool:
        """Register a peer and adopt the peers it returns (one-hop discovery)."""
        resp = post_json(f"http://{address}/peers", {"peer": self.address})
        if resp is None:
            return False
        self.register_peer(address)
        for p in resp.get("peers", []):
            self.register_peer(p)
        return True

    # ---------- gossip ----------

    def broadcast_transaction(self, tx: Transaction) -> None:
        payload = {"transaction": tx.to_dict(), "relay": False}
        for peer in list(self.peers):
            post_json(f"http://{peer}/transactions", payload)

    def broadcast_block(self, block: Block) -> None:
        payload = {"block": block.to_dict()}
        for peer in list(self.peers):
            post_json(f"http://{peer}/blocks", payload)

    # ---------- consensus / sync ----------

    def fetch_remote_chain(self, peer: str):
        """Return a peer's chain as Block objects, or None if unreachable."""
        data = get_json(f"http://{peer}/chain")
        if not data or "chain" not in data:
            return None
        try:
            return Blockchain.chain_from_dicts(data["chain"])
        except Exception:
            return None

    def sync_with_peers(self) -> dict:
        """Pull every peer's chain; adopt the longest valid one."""
        best = self.blockchain.chain
        best_peer = None
        for peer in list(self.peers):
            remote = self.fetch_remote_chain(peer)
            if remote and len(remote) > len(best):
                best, best_peer = remote, peer
        replaced = False
        if best is not self.blockchain.chain:
            replaced = self.blockchain.replace_chain(best)
        return {
            "replaced": replaced,
            "best_peer": best_peer,
            "length": len(self.blockchain.chain),
        }


class _NodeRequestHandler(BaseHTTPRequestHandler):
    """Thin HTTP layer — all logic delegates to the BlockchainNode on the server."""

    @property
    def node(self) -> BlockchainNode:
        return self.server.node

    def log_message(self, fmt, *args):
        print(f"[node :{self.node.port}] {fmt % args}")

    # ---------- helpers ----------

    def _send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return None

    # ---------- GET ----------

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/chain":
            self._send_json(self.node.blockchain.to_dict())
        elif path == "/mempool":
            txs = [t.to_dict() for t in self.node.blockchain.pending_transactions]
            self._send_json({"length": len(txs), "transactions": txs})
        else:
            self._send_json({"error": "not found"}, status=404)

    # ---------- POST ----------

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_json()
        if body is None:
            self._send_json({"error": "bad json"}, status=400)
            return

        handler = {
            "/peers": self._handle_peers,
            "/transactions": self._handle_transaction,
            "/blocks": self._handle_block,
            "/mine": self._handle_mine,
            "/sync": self._handle_sync,
        }.get(path)
        if handler is None:
            self._send_json({"error": "not found"}, status=404)
        else:
            handler(body)

    def _handle_peers(self, body: dict) -> None:
        peer = body.get("peer")
        if not peer:
            self._send_json({"error": "missing 'peer'"}, status=400)
            return
        self.node.register_peer(peer)
        self._send_json({"peers": sorted(self.node.peers)})

    def _handle_transaction(self, body: dict) -> None:
        try:
            tx = Transaction.from_dict(body["transaction"])
        except Exception:
            self._send_json({"error": "bad transaction"}, status=400)
            return
        if not self.node.blockchain.submit_transaction(tx):
            self._send_json({"accepted": False, "reason": "invalid signature"},
                            status=400)
            return
        if body.get("relay", True):
            self.node.broadcast_transaction(tx)
        self._send_json({"accepted": True,
                         "mempool": len(self.node.blockchain.pending_transactions)})

    def _handle_block(self, body: dict) -> None:
        try:
            block = Block.from_dict(body["block"])
        except Exception:
            self._send_json({"error": "bad block"}, status=400)
            return
        if self.node.blockchain.add_block(block):
            self._send_json({"appended": True,
                             "height": len(self.node.blockchain.chain)})
            return
        # Not a direct extension — maybe we're behind; pull the longest chain.
        if block.index > self.node.blockchain.last_block.index:
            result = self.node.sync_with_peers()
            self._send_json({"appended": False, "synced": result})
        else:
            self._send_json({"appended": False, "reason": "stale or invalid"},
                            status=409)

    def _handle_mine(self, body: dict) -> None:
        miner = body.get("miner", self.node.address)
        block = self.node.blockchain.mine_pending_transactions(miner)
        self.node.broadcast_block(block)
        self._send_json({"mined": True, "block": block.to_dict()})

    def _handle_sync(self, _body: dict) -> None:
        self._send_json(self.node.sync_with_peers())


def main():
    parser = argparse.ArgumentParser(description="Educational blockchain node")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--difficulty", type=int, default=4)
    parser.add_argument("--peer", action="append", default=[],
                        help="bootstrap peer address, e.g. 127.0.0.1:5001")
    args = parser.parse_args()

    node = BlockchainNode(args.host, args.port, difficulty=args.difficulty)
    for peer in args.peer:
        node.connect_to_peer(peer)
    print(f"节点已启动: http://{node.address}  peers={sorted(node.peers)}")
    try:
        node.serve_forever()
    except KeyboardInterrupt:
        node.stop()


if __name__ == "__main__":
    main()
