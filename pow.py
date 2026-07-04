"""
YRC-Hash: the YourCoin proof-of-work function.

Design: double-SHA256(scrypt(header)), i.e. the same "memory-hard wrapper"
approach Litecoin popularized to make GPU/CPU mining practical while
resisting cheap ASIC specialization. This reference implementation runs
scrypt(N=1024, r=1, p=1) which is intentionally lightweight enough to mine
in pure Python on a CPU for demonstration/testnet purposes.

Difficulty is represented as a raw 256-bit integer target (lower = harder),
rather than Bitcoin's compact `nBits` encoding -- functionally equivalent,
simpler to reason about, and avoids float/rounding edge cases in this
reference implementation.

A GPU-optimized mainnet build would replace this module with a real
KAWPOW/ProgPoW DAG-based kernel (OpenCL/CUDA) while keeping the exact same
interface (`yrc_hash(header_bytes) -> 32 bytes`, `hash_meets_target`).
"""
import hashlib


def yrc_hash(header_bytes: bytes) -> bytes:
    salt = hashlib.sha256(header_bytes).digest()[:16]
    scrypt_out = hashlib.scrypt(header_bytes, salt=salt, n=1024, r=1, p=1, dklen=32)
    return hashlib.sha256(scrypt_out).digest()


def hash_meets_target(hash_bytes: bytes, target: int) -> bool:
    return int.from_bytes(hash_bytes, "big") <= target


def difficulty_from_target(target: int, genesis_target: int) -> float:
    """Human-readable 'difficulty' relative to genesis (like Bitcoin's diff 1.0)."""
    if target <= 0:
        return float("inf")
    return genesis_target / target
