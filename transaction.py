import hashlib
import json
import time

from core import crypto_utils


class TxInput:
    __slots__ = ("txid", "index", "signature", "pubkey")

    def __init__(self, txid, index, signature=None, pubkey=None):
        self.txid = txid
        self.index = index
        self.signature = signature  # hex string
        self.pubkey = pubkey        # hex string (compressed pubkey)

    def to_dict(self):
        return {"txid": self.txid, "index": self.index, "signature": self.signature, "pubkey": self.pubkey}

    @staticmethod
    def from_dict(d):
        return TxInput(d["txid"], d["index"], d.get("signature"), d.get("pubkey"))


class TxOutput:
    __slots__ = ("address", "amount")

    def __init__(self, address, amount):
        self.address = address
        self.amount = int(amount)

    def to_dict(self):
        return {"address": self.address, "amount": self.amount}

    @staticmethod
    def from_dict(d):
        return TxOutput(d["address"], d["amount"])


class Transaction:
    def __init__(self, inputs, outputs, timestamp=None, coinbase=False, memo=""):
        self.inputs = inputs
        self.outputs = outputs
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.coinbase = coinbase
        self.memo = memo  # used to make coinbase txids unique (extra nonce / genesis message)
        self.txid = self.compute_txid()

    def _unsigned_payload(self):
        return {
            "inputs": [{"txid": i.txid, "index": i.index} for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "timestamp": self.timestamp,
            "coinbase": self.coinbase,
            "memo": self.memo,
        }

    def signing_hash(self) -> bytes:
        payload = json.dumps(self._unsigned_payload(), sort_keys=True).encode()
        return hashlib.sha256(payload).digest()

    def compute_txid(self) -> str:
        payload = json.dumps(self._unsigned_payload(), sort_keys=True).encode()
        return hashlib.sha256(hashlib.sha256(payload).digest()).hexdigest()

    def sign_input(self, index: int, private_key):
        sighash = self.signing_hash()
        sig = crypto_utils.sign(private_key, sighash)
        self.inputs[index].signature = sig.hex()
        self.inputs[index].pubkey = crypto_utils.public_key_compressed(private_key).hex()

    def verify_input(self, index: int) -> bool:
        txin = self.inputs[index]
        if not txin.signature or not txin.pubkey:
            return False
        try:
            return crypto_utils.verify(
                bytes.fromhex(txin.pubkey), bytes.fromhex(txin.signature), self.signing_hash()
            )
        except Exception:
            return False

    def to_dict(self):
        return {
            "txid": self.txid,
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "timestamp": self.timestamp,
            "coinbase": self.coinbase,
            "memo": self.memo,
        }

    @staticmethod
    def from_dict(d):
        tx = Transaction(
            [TxInput.from_dict(i) for i in d["inputs"]],
            [TxOutput.from_dict(o) for o in d["outputs"]],
            timestamp=d["timestamp"],
            coinbase=d["coinbase"],
            memo=d.get("memo", ""),
        )
        tx.txid = d["txid"]
        return tx

    @staticmethod
    def create_coinbase(address: str, amount: int, memo: str = ""):
        txin = TxInput(txid="0" * 64, index=-1)
        txout = TxOutput(address, amount)
        return Transaction([txin], [txout], coinbase=True, memo=memo or str(time.time()))
