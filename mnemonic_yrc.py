"""
YRC seed phrase system.

Modeled on BIP39 (entropy -> checksum -> word-indices -> mnemonic, and
mnemonic -> PBKDF2-HMAC-SHA512 -> seed), but uses a procedurally generated,
self-contained 2048-word list instead of the official BIP39 English wordlist
(which would require bundling an external data file / network fetch).

This is NOT cross-compatible with BIP39 wallets, but is a fully functional,
deterministic, checksum-protected seed phrase scheme with the same security
properties (128 bits entropy + 4-bit checksum -> 12 words).
"""
import hashlib
import secrets

_CONSONANTS = "bcdfghjklmnpqrstvwxyz"   # 21
_VOWELS = "aeiou"                        # 5


def _word_for_index(i: int) -> str:
    # Bijective base mapping of an 11-bit index (0-2047) onto a pronounceable
    # 4-letter consonant-vowel-consonant-vowel token. 21*5*21*5 = 11025 >= 2048.
    c1 = _CONSONANTS[i % 21]
    i //= 21
    v1 = _VOWELS[i % 5]
    i //= 5
    c2 = _CONSONANTS[i % 21]
    i //= 21
    v2 = _VOWELS[i % 5]
    return c1 + v1 + c2 + v2


WORDLIST = [_word_for_index(i) for i in range(2048)]
WORD_INDEX = {w: i for i, w in enumerate(WORDLIST)}


def generate_mnemonic(strength_bits: int = 128) -> str:
    if strength_bits % 32 != 0 or not (128 <= strength_bits <= 256):
        raise ValueError("strength_bits must be a multiple of 32 between 128 and 256")
    entropy = secrets.token_bytes(strength_bits // 8)
    return entropy_to_mnemonic(entropy)


def entropy_to_mnemonic(entropy: bytes) -> str:
    entropy_bits = len(entropy) * 8
    checksum_bits = entropy_bits // 32
    checksum = hashlib.sha256(entropy).digest()
    checksum_int = int.from_bytes(checksum, "big") >> (256 - checksum_bits)

    combined = (int.from_bytes(entropy, "big") << checksum_bits) | checksum_int
    total_bits = entropy_bits + checksum_bits
    n_words = total_bits // 11

    words = []
    for i in range(n_words):
        shift = total_bits - (i + 1) * 11
        idx = (combined >> shift) & 0x7FF
        words.append(WORDLIST[idx])
    return " ".join(words)


def mnemonic_to_entropy(mnemonic: str) -> bytes:
    words = mnemonic.strip().split()
    n_words = len(words)
    total_bits = n_words * 11
    entropy_bits = total_bits * 32 // 33
    checksum_bits = total_bits - entropy_bits

    combined = 0
    for w in words:
        if w not in WORD_INDEX:
            raise ValueError(f"unknown word in mnemonic: {w}")
        combined = (combined << 11) | WORD_INDEX[w]

    entropy_int = combined >> checksum_bits
    entropy = entropy_int.to_bytes(entropy_bits // 8, "big")

    checksum_int = combined & ((1 << checksum_bits) - 1)
    expected_checksum = int.from_bytes(hashlib.sha256(entropy).digest(), "big") >> (256 - checksum_bits)
    if checksum_int != expected_checksum:
        raise ValueError("invalid mnemonic checksum")
    return entropy


def mnemonic_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha512",
        mnemonic.encode("utf-8"),
        ("yourcoin-mnemonic" + passphrase).encode("utf-8"),
        2048,
        dklen=64,
    )


def validate_mnemonic(mnemonic: str) -> bool:
    try:
        mnemonic_to_entropy(mnemonic)
        return True
    except Exception:
        return False
