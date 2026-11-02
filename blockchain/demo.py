# -*- coding: utf-8 -*-
"""End-to-end demo scenarios.

  python -m blockchain.demo            # run all three scenarios
  python -m blockchain.demo single     # only the single-node scenario
  python -m blockchain.demo sync       # only the two-node sync scenario
  python -m blockchain.demo tamper     # only the tamper-detection scenario
"""
import argparse
import sys
import time

from .chain import Blockchain
from .crypto_utils import generate_rsa_keypair, public_key_to_pem
from .node import BlockchainNode, get_json, post_json
from .transaction import Transaction

DEMO_DIFFICULTY = 4


def _print_chain(bc: Blockchain, title: str) -> None:
    print(f"\n--- {title} (length={len(bc.chain)}) ---")
    for b in bc.chain:
        names = ["coinbase" if t.sender == "MINING_REWARD"
                 else f"...{t.sender[-15:].strip()}->{t.recipient}"
                 for t in b.transactions]
        print(f"  #{b.index} nonce={b.nonce:<8} hash={b.compute_hash()[:16]}...  "
              f"prev={b.previous_hash[:16]}...  txs={names}")


def _make_signed_tx(priv, pub, recipient: str, amount: float) -> Transaction:
    tx = Transaction(sender=public_key_to_pem(pub), recipient=recipient,
                     amount=amount)
    tx.sign(priv)
    return tx


# ---------------------------------------------------------------- scenario 1

def demo_single_node() -> Blockchain:
    print("=" * 60)
    print("场景 1: 单节点 —— 签名交易 + PoW 出块")
    print("=" * 60)

    alice_priv, alice_pub = generate_rsa_keypair()
    bob_priv, bob_pub = generate_rsa_keypair()
    mallory_priv, _ = generate_rsa_keypair()
    print("已生成 3 个 RSA 钱包: alice, bob, mallory")

    bc = Blockchain(difficulty=DEMO_DIFFICULTY)
    print(f"创世区块: hash={bc.last_block.compute_hash()[:16]}... "
          f"(难度 {DEMO_DIFFICULTY} 个前导零)")

    tx1 = _make_signed_tx(alice_priv, alice_pub, "bob", 10.0)
    tx2 = _make_signed_tx(bob_priv, bob_pub, "alice", 3.5)
    # Forgery: claims to be from alice but signed by mallory's key -> rejected
    forged = _make_signed_tx(mallory_priv, alice_pub, "mallory", 999.0)

    print("\n提交交易:")
    for label, tx in [("alice->bob 10.0", tx1), ("bob->alice 3.5", tx2),
                      ("伪造 alice->mallory 999", forged)]:
        ok = bc.submit_transaction(tx)
        print(f"  {label:<28} -> {'已入 mempool' if ok else '验签失败，被拒绝'}")

    print("\n开始挖矿 (打包 mempool + coinbase 奖励)...")
    t0 = time.time()
    block = bc.mine_pending_transactions("miner-paco")
    print(f"出块成功: #{block.index} nonce={block.nonce} "
          f"hash={block.compute_hash()[:20]}... 耗时 {time.time()-t0:.2f}s")

    _print_chain(bc, "链状态")
    print(f"\nvalidate_chain: {'通过' if bc.validate_chain() else '失败'}")
    return bc


# ---------------------------------------------------------------- scenario 2

def demo_tamper() -> None:
    print("\n" + "=" * 60)
    print("场景 2: 篡改历史交易 —— 哈希链断裂检测")
    print("=" * 60)
    bc = demo_single_node()
    print("\n篡改区块 #1 中的交易金额 10.0 -> 10000 ...")
    bc.chain[1].transactions[1].amount = 10000.0
    ok = bc.validate_chain()
    print(f"validate_chain: {'通过 (异常!)' if ok else '失败 —— 检测到篡改 ✔'}")


# ---------------------------------------------------------------- scenario 3

def demo_two_node_sync() -> None:
    print("\n" + "=" * 60)
    print("场景 3: 双节点 —— 广播出块 + 最长链同步")
    print("=" * 60)

    node_a = BlockchainNode("127.0.0.1", 5001, difficulty=DEMO_DIFFICULTY)
    node_b = BlockchainNode("127.0.0.1", 5002, difficulty=DEMO_DIFFICULTY)
    node_a.start()
    node_b.start()
    time.sleep(0.3)
    print(f"节点 A 启动于 :5001, 节点 B 启动于 :5002 (暂未互相注册)")

    try:
        alice_priv, alice_pub = generate_rsa_keypair()
        tx = _make_signed_tx(alice_priv, alice_pub, "bob", 7.0)

        # A mines two blocks while B is still isolated
        post_json(f"http://{node_a.address}/transactions",
                  {"transaction": tx.to_dict(), "relay": False})
        for i in range(2):
            print(f"\n节点 A 挖第 {i+1} 块...")
            t0 = time.time()
            resp = post_json(f"http://{node_a.address}/mine", {"miner": "miner-A"})
            print(f"  A 出块 #{resp['block']['index']} "
                  f"hash={resp['block']['hash'][:16]}... "
                  f"耗时 {time.time()-t0:.2f}s")

        print(f"\n链长: A={len(node_a.blockchain.chain)} "
              f"B={len(node_b.blockchain.chain)} (B 还只有创世块)")

        # Register peers both ways, then B syncs to the longest chain
        node_a.connect_to_peer(node_b.address)
        node_b.connect_to_peer(node_a.address)
        print(f"互注册完成: A.peers={sorted(node_a.peers)} "
              f"B.peers={sorted(node_b.peers)}")

        print("\n节点 B 执行 /sync ...")
        resp = post_json(f"http://{node_b.address}/sync", {})
        print(f"  结果: replaced={resp['replaced']} "
              f"best_peer={resp['best_peer']} length={resp['length']}")

        tip_a = node_a.blockchain.last_block.compute_hash()
        tip_b = node_b.blockchain.last_block.compute_hash()
        print(f"  A 链头={tip_a[:20]}...")
        print(f"  B 链头={tip_b[:20]}...")
        print(f"  两条链收敛: {'一致 ✔' if tip_a == tip_b else '不一致 ✘'}")

        # Now show live broadcast: new tx on A relays to B's mempool,
        # A's next mined block auto-appends on B
        tx2 = _make_signed_tx(alice_priv, alice_pub, "carol", 1.25)
        print("\n向 A 提交新交易 (relay=true, 会广播到 B 的 mempool)...")
        post_json(f"http://{node_a.address}/transactions",
                  {"transaction": tx2.to_dict()})
        mp_b = get_json(f"http://{node_b.address}/mempool")
        print(f"  B 的 mempool 现有 {mp_b['length']} 笔交易")

        print("节点 A 再挖一块并广播...")
        post_json(f"http://{node_a.address}/mine", {"miner": "miner-A"})
        time.sleep(0.3)
        same = (node_a.blockchain.last_block.compute_hash()
                == node_b.blockchain.last_block.compute_hash())
        print(f"  广播后链高 A={len(node_a.blockchain.chain)} "
              f"B={len(node_b.blockchain.chain)}, "
              f"链头{'一致 ✔' if same else '不一致 ✘'}")

        _print_chain(node_b.blockchain, "节点 B 的最终链")
    finally:
        node_a.stop()
        node_b.stop()


def main():
    # Force UTF-8 output so Chinese text renders in redirected/captured streams
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Blockchain demo scenarios")
    parser.add_argument("scenario", nargs="?", default="all",
                        choices=["all", "single", "tamper", "sync"])
    args = parser.parse_args()

    if args.scenario in ("all", "single"):
        demo_single_node()
    if args.scenario in ("all", "tamper"):
        demo_tamper()
    if args.scenario in ("all", "sync"):
        demo_two_node_sync()


if __name__ == "__main__":
    sys.exit(main())
