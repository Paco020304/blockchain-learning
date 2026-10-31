# -*- coding: utf-8 -*-
"""
POW (Proof of Work) + RSA 签名验证实验
1. 昵称 + nonce 不断做 SHA256，直到哈希以 4 个 0 开头，打印耗时
2. 同上，直到以 5 个 0 开头，打印耗时
3. 生成 RSA 公私钥对，用私钥对满足 POW 的 昵称+nonce 签名，用公钥验证
"""
import hashlib
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

NICKNAME = "Paco020304"


def proof_of_work(nickname: str, zeros: int):
    """不断递增 nonce 做 SHA256，直到哈希以 zeros 个 '0' 开头。返回 (nonce, hash, 耗时秒)。"""
    target = "0" * zeros
    nonce = 0
    start = time.time()
    while True:
        data = f"{nickname}{nonce}".encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        if digest.startswith(target):
            elapsed = time.time() - start
            return nonce, digest, elapsed
        nonce += 1


def main():
    print(f"昵称: {NICKNAME}\n")

    # ---- POW: 4 个前导零 ----
    nonce4, hash4, t4 = proof_of_work(NICKNAME, 4)
    print(f"[POW 4 个 0] 找到 nonce = {nonce4}")
    print(f"  消息: {NICKNAME}{nonce4}")
    print(f"  SHA256: {hash4}")
    print(f"  耗时: {t4:.4f} 秒\n")

    # ---- POW: 5 个前导零 ----
    nonce5, hash5, t5 = proof_of_work(NICKNAME, 5)
    print(f"[POW 5 个 0] 找到 nonce = {nonce5}")
    print(f"  消息: {NICKNAME}{nonce5}")
    print(f"  SHA256: {hash5}")
    print(f"  耗时: {t5:.4f} 秒\n")

    # ---- RSA: 生成密钥对 ----
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    print("已生成 RSA-2048 公私钥对\n")

    # ---- 用私钥对满足 POW 的 昵称+nonce 签名（这里对 5 个 0 的结果签名）----
    message = f"{NICKNAME}{nonce5}".encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    print(f"签名消息: {message.decode()}")
    print(f"签名 (hex, 前 64 字节): {signature.hex()[:128]}...\n")

    # ---- 用公钥验证 ----
    try:
        public_key.verify(
            signature,
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        print("公钥验证结果: 签名有效 ✔")
    except Exception as e:
        print(f"公钥验证结果: 签名无效 ✘ ({e})")

    # 顺带验证：篡改消息后应验证失败
    try:
        public_key.verify(
            signature,
            b"tampered",
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        print("篡改消息验证: 意外通过 (异常)")
    except Exception:
        print("篡改消息验证: 按预期失败 (签名只对该 昵称+nonce 有效)")


if __name__ == "__main__":
    main()
