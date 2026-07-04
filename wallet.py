import hashlib

import config
from core import crypto_utils
from core.base58 import b58check_encode, b58check_decode
from core.transaction import Transaction, TxInput, TxOutput
from wallet.mnemonic_yrc import generate_mnemonic, mnemonic_to_seed, validate_mnemonic


def pubkey_to_address(pubkey_bytes: bytes, network: str = "mainnet") -> str:
    sha = hashlib.sha256(pubkey_bytes).digest()
    ripemd = hashlib.new("ripemd160", sha).digest()
    payload = config.ADDRESS_PREFIX[network] + ripemd
    return b58check_encode(payload)


def validate_address(address: str, network: str = "mainnet") -> bool:
    try:
        payload = b58check_decode(address)
        return payload[:1] == config.ADDRESS_PREFIX[network] and len(payload) == 21
    except Exception:
        return False


class Wallet:
    def __init__(self, network="mainnet", mnemonic_phrase=None):
        self.network = network
        self.mnemonic = mnemonic_phrase or generate_mnemonic(128)
        if not validate_mnemonic(self.mnemonic):
            raise ValueError("invalid seed phrase (checksum failed)")
        seed = mnemonic_to_seed(self.mnemonic)
        secret_int = int.from_bytes(hashlib.sha256(seed).digest(), "big") % (2 ** 256 - 1)
        self.private_key = crypto_utils.private_key_from_int(secret_int)
        self.pubkey_compressed = crypto_utils.public_key_compressed(self.private_key)
        self.address = pubkey_to_address(self.pubkey_compressed, network)

    def export_private_key_wif(self) -> str:
        priv_bytes = crypto_utils.private_key_to_bytes(self.private_key)
        version = config.WIF_PREFIX[self.network]
        return b58check_encode(version + priv_bytes)

    @staticmethod
    def from_wif(wif: str, network: str = "mainnet") -> "Wallet":
        payload = b58check_decode(wif)
        priv_bytes = payload[1:]
        secret_int = int.from_bytes(priv_bytes, "big")
        w = Wallet.__new__(Wallet)
        w.network = network
        w.mnemonic = None
        w.private_key = crypto_utils.private_key_from_int(secret_int)
        w.pubkey_compressed = crypto_utils.public_key_compressed(w.private_key)
        w.address = pubkey_to_address(w.pubkey_compressed, network)
        return w

    def to_dict(self) -> dict:
        return {"address": self.address, "mnemonic": self.mnemonic, "network": self.network}


def build_transaction(chain_source, wallet: Wallet, to_address: str, amount: int, fee: int = None) -> Transaction:
    """
    chain_source: anything exposing get_utxos_for_address(address) -> {"txid:idx": {"address","amount"}}
    (works with a local Blockchain instance OR a remote-RPC proxy -- see cli/wallet_cli.py)
    """
    fee = fee if fee is not None else config.MIN_RELAY_FEE
    utxos = chain_source.get_utxos_for_address(wallet.address)
    selected, total = [], 0
    for key, utxo in utxos.items():
        selected.append((key, utxo))
        total += utxo["amount"]
        if total >= amount + fee:
            break
    if total < amount + fee:
        raise ValueError(f"insufficient funds: have {total}, need {amount + fee}")

    inputs = []
    for key, _utxo in selected:
        txid, index = key.rsplit(":", 1)
        inputs.append(TxInput(txid, int(index)))

    outputs = [TxOutput(to_address, amount)]
    change = total - amount - fee
    if change > 0:
        outputs.append(TxOutput(wallet.address, change))

    tx = Transaction(inputs, outputs)
    for i in range(len(inputs)):
        tx.sign_input(i, wallet.private_key)
    tx.txid = tx.compute_txid()
    return tx
