"""
Base58Check encoding/decoding -- implemented from scratch (no external dependency),
identical in spirit to the scheme used by Bitcoin-derived coins.
"""
import hashlib

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    res = ""
    while n > 0:
        n, r = divmod(n, 58)
        res = ALPHABET[r] + res
    pad = 0
    for byte in b:
        if byte == 0:
            pad += 1
        else:
            break
    return "1" * pad + res


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        if ch not in ALPHABET:
            raise ValueError(f"invalid base58 character: {ch}")
        n = n * 58 + ALPHABET.index(ch)
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n > 0 else b""
    pad = 0
    for ch in s:
        if ch == "1":
            pad += 1
        else:
            break
    return b"\x00" * pad + body


def b58check_encode(payload: bytes) -> str:
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return b58encode(payload + checksum)


def b58check_decode(s: str) -> bytes:
    raw = b58decode(s)
    payload, checksum = raw[:-4], raw[-4:]
    calc = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    if calc != checksum:
        raise ValueError("bad base58check checksum")
    return payload
