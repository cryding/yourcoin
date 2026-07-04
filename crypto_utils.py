"""
SECP256K1 key generation, signing, and verification.
Built on the `cryptography` package (already vendored/available), avoiding
any dependency on packages that require network access to install.
"""
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.exceptions import InvalidSignature

CURVE = ec.SECP256K1()


def generate_private_key():
    return ec.generate_private_key(CURVE)


def private_key_from_int(secret_int: int):
    return ec.derive_private_key(secret_int, CURVE)


def private_key_to_int(private_key) -> int:
    return private_key.private_numbers().private_value


def private_key_to_bytes(private_key) -> bytes:
    return private_key_to_int(private_key).to_bytes(32, "big")


def public_key_compressed(private_key_or_public_key) -> bytes:
    if hasattr(private_key_or_public_key, "public_key"):
        pub = private_key_or_public_key.public_key()
    else:
        pub = private_key_or_public_key
    return pub.public_bytes(Encoding.X962, PublicFormat.CompressedPoint)


def public_key_from_compressed(pubkey_bytes: bytes):
    return ec.EllipticCurvePublicKey.from_encoded_point(CURVE, pubkey_bytes)


def sign(private_key, message: bytes) -> bytes:
    return private_key.sign(message, ec.ECDSA(hashes.SHA256()))


def verify(pubkey_bytes: bytes, signature: bytes, message: bytes) -> bool:
    try:
        pub = public_key_from_compressed(pubkey_bytes)
        pub.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, Exception):
        return False
