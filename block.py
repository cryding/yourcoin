import hashlib
import time

from core.pow import yrc_hash
from core.transaction import Transaction


class BlockHeader:
    __slots__ = ("version", "prev_hash", "merkle_root", "timestamp", "bits", "nonce")

    def __init__(self, version, prev_hash, merkle_root, timestamp, bits, nonce=0):
        self.version = version
        self.prev_hash = prev_hash
        self.merkle_root = merkle_root
        self.timestamp = timestamp
        self.bits = bits          # raw 256-bit integer target
        self.nonce = nonce

    def serialize(self) -> bytes:
        payload = f"{self.version}|{self.prev_hash}|{self.merkle_root}|{self.timestamp}|{self.bits}|{self.nonce}"
        return payload.encode()

    def hash(self) -> str:
        return yrc_hash(self.serialize()).hex()

    def to_dict(self):
        return {
            "version": self.version,
            "prev_hash": self.prev_hash,
            "merkle_root": self.merkle_root,
            "timestamp": self.timestamp,
            "bits": self.bits,
            "nonce": self.nonce,
        }

    @staticmethod
    def from_dict(d):
        return BlockHeader(d["version"], d["prev_hash"], d["merkle_root"], d["timestamp"], d["bits"], d["nonce"])


def merkle_root(txids):
    if not txids:
        return hashlib.sha256(b"").hexdigest()
    layer = list(txids)
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [hashlib.sha256((layer[i] + layer[i + 1]).encode()).hexdigest() for i in range(0, len(layer), 2)]
    return layer[0]


class Block:
    def __init__(self, header: BlockHeader, transactions, height: int):
        self.header = header
        self.transactions = transactions
        self.height = height

    def hash(self) -> str:
        return self.header.hash()

    def to_dict(self):
        return {
            "header": self.header.to_dict(),
            "transactions": [t.to_dict() for t in self.transactions],
            "height": self.height,
        }

    @staticmethod
    def from_dict(d):
        header = BlockHeader.from_dict(d["header"])
        txs = [Transaction.from_dict(t) for t in d["transactions"]]
        return Block(header, txs, d["height"])

    @staticmethod
    def create(prev_hash: str, transactions, height: int, target: int, version: int = 1):
        txids = [t.txid for t in transactions]
        root = merkle_root(txids)
        header = BlockHeader(version, prev_hash, root, time.time(), target, nonce=0)
        return Block(header, transactions, height)
