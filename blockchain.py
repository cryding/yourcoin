import json
import os
import threading

import config
from core.block import Block, BlockHeader, merkle_root
from core.pow import yrc_hash, hash_meets_target
from core.transaction import Transaction


class Blockchain:
    def __init__(self, network="mainnet", datadir=None):
        self.network = network
        self.datadir = datadir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", network)
        os.makedirs(self.datadir, exist_ok=True)
        self.chain_file = os.path.join(self.datadir, "chain.json")
        self.lock = threading.RLock()
        self.chain = []
        self.utxo_set = {}   # "txid:index" -> {"address":..., "amount":...}
        self.mempool = {}    # txid -> Transaction

        if os.path.exists(self.chain_file):
            self.load()
        else:
            genesis = self._mine_genesis()
            self.chain.append(genesis)
            self._apply_block_utxo(genesis)
            self.save()

    # ---------------------------------------------------------- genesis
    def _mine_genesis(self) -> Block:
        # Timestamp must be pinned explicitly -- otherwise every node would
        # independently generate a different genesis coinbase txid (since
        # Transaction defaults timestamp to time.time()), producing a
        # different genesis hash and permanently forking the network before
        # it even starts.
        coinbase = Transaction.create_coinbase(
            address=config.GENESIS_BURN_ADDRESS_PLACEHOLDER,
            amount=config.INITIAL_REWARD,
            memo=config.GENESIS_MESSAGE,
        )
        coinbase.timestamp = config.GENESIS_TIMESTAMP
        coinbase.txid = coinbase.compute_txid()
        target = config.GENESIS_TARGET
        header = BlockHeader(1, "0" * 64, merkle_root([coinbase.txid]), config.GENESIS_TIMESTAMP, target, nonce=0)
        nonce = 0
        while True:
            header.nonce = nonce
            if hash_meets_target(yrc_hash(header.serialize()), target):
                break
            nonce += 1
        return Block(header, [coinbase], 0)

    # ---------------------------------------------------------- persistence
    def save(self):
        with self.lock:
            data = {"chain": [b.to_dict() for b in self.chain], "utxo": self.utxo_set}
            tmp = self.chain_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, self.chain_file)

    def load(self):
        with open(self.chain_file) as f:
            data = json.load(f)
        self.chain = [Block.from_dict(b) for b in data["chain"]]
        self.utxo_set = data["utxo"]

    # ---------------------------------------------------------- difficulty (DGW-style, every block)
    def current_target(self) -> int:
        with self.lock:
            if len(self.chain) < 2:
                return self.chain[-1].header.bits
            window = self.chain[-config.DIFFICULTY_WINDOW:] if len(self.chain) > config.DIFFICULTY_WINDOW else self.chain[:]
            if len(window) < 2:
                return self.chain[-1].header.bits
            actual_time = window[-1].header.timestamp - window[0].header.timestamp
            n_intervals = len(window) - 1
            avg_time = max(actual_time / n_intervals, 1e-6) if n_intervals else config.BLOCK_TIME_TARGET
            ratio = avg_time / config.BLOCK_TIME_TARGET
            ratio = max(0.25, min(4.0, ratio))  # clamp swing per block, like DGW/Dash
            new_target = int(self.chain[-1].header.bits * ratio)
            new_target = max(1, min(new_target, config.MAX_TARGET))
            return new_target

    # ---------------------------------------------------------- reward schedule
    def block_reward(self, height: int) -> int:
        halvings = height // config.HALVING_INTERVAL
        if halvings >= 64:
            return 0
        return config.INITIAL_REWARD >> halvings

    # ---------------------------------------------------------- UTXO helpers
    def get_utxos_for_address(self, address: str) -> dict:
        with self.lock:
            return {k: v for k, v in self.utxo_set.items() if v["address"] == address}

    def get_balance(self, address: str) -> int:
        return sum(v["amount"] for v in self.get_utxos_for_address(address).values())

    def _apply_block_utxo(self, block: Block):
        for tx in block.transactions:
            if not tx.coinbase:
                for txin in tx.inputs:
                    self.utxo_set.pop(f"{txin.txid}:{txin.index}", None)
            for idx, out in enumerate(tx.outputs):
                self.utxo_set[f"{tx.txid}:{idx}"] = {"address": out.address, "amount": out.amount}

    # ---------------------------------------------------------- validation
    def validate_transaction(self, tx: Transaction, spent_in_batch=None) -> bool:
        if tx.coinbase:
            return True
        spent_in_batch = spent_in_batch if spent_in_batch is not None else set()
        total_in = 0
        for idx, txin in enumerate(tx.inputs):
            key = f"{txin.txid}:{txin.index}"
            if key in spent_in_batch:
                return False  # double-spend protection: same output spent twice
            utxo = self.utxo_set.get(key)
            if not utxo:
                return False  # unknown or already-spent output
            if not tx.verify_input(idx):
                return False  # digital signature verification
            total_in += utxo["amount"]
            spent_in_batch.add(key)
        total_out = sum(o.amount for o in tx.outputs)
        if total_out > total_in:
            return False
        for o in tx.outputs:
            if o.amount < config.DUST_THRESHOLD:
                return False  # anti-spam dust filter
        fee = total_in - total_out
        if fee < 0:
            return False
        return True

    def validate_block(self, block: Block):
        with self.lock:
            if block.height != len(self.chain):
                return False, "bad height (possible fork / stale template)"
            if block.header.prev_hash != self.chain[-1].hash():
                return False, "prev_hash does not match tip"
            expected_target = self.current_target()
            if block.header.bits != expected_target:
                return False, "difficulty target mismatch"
            h = yrc_hash(block.header.serialize())
            if not hash_meets_target(h, block.header.bits):
                return False, "proof-of-work does not meet target"
            txids = [t.txid for t in block.transactions]
            if merkle_root(txids) != block.header.merkle_root:
                return False, "merkle root mismatch"
            coinbase_txs = [t for t in block.transactions if t.coinbase]
            if len(coinbase_txs) != 1:
                return False, "block must contain exactly one coinbase transaction"

            spent = set()
            fees = 0
            for tx in block.transactions:
                if tx.coinbase:
                    continue
                if not self.validate_transaction(tx, spent):
                    return False, f"invalid transaction {tx.txid}"
                total_in = sum(self.utxo_set[f"{i.txid}:{i.index}"]["amount"] for i in tx.inputs)
                total_out = sum(o.amount for o in tx.outputs)
                fees += total_in - total_out

            expected_reward = self.block_reward(block.height)
            coinbase_out = sum(o.amount for o in coinbase_txs[0].outputs)
            if coinbase_out > expected_reward + fees:
                return False, "coinbase pays more than reward + fees"
            return True, "ok"

    def add_block(self, block: Block):
        with self.lock:
            ok, reason = self.validate_block(block)
            if not ok:
                return False, reason
            self.chain.append(block)
            self._apply_block_utxo(block)
            for tx in block.transactions:
                self.mempool.pop(tx.txid, None)
            self.save()
            return True, "accepted"

    def add_transaction_to_mempool(self, tx: Transaction):
        with self.lock:
            if tx.txid in self.mempool:
                return False, "already in mempool"
            if not self.validate_transaction(tx):
                return False, "invalid transaction"
            self.mempool[tx.txid] = tx
            return True, "added to mempool"

    def create_block_template(self, miner_address: str) -> Block:
        from wallet.wallet import validate_address
        if not validate_address(miner_address, self.network):
            raise ValueError(f"invalid {self.network} address for mining reward: {miner_address}")
        with self.lock:
            height = len(self.chain)
            reward = self.block_reward(height)
            txs = list(self.mempool.values())
            fees = 0
            for tx in txs:
                total_in = sum(self.utxo_set.get(f"{i.txid}:{i.index}", {"amount": 0})["amount"] for i in tx.inputs)
                total_out = sum(o.amount for o in tx.outputs)
                fees += max(0, total_in - total_out)
            coinbase = Transaction.create_coinbase(miner_address, reward + fees)
            target = self.current_target()
            return Block.create(self.chain[-1].hash(), [coinbase] + txs, height, target)

    # ---------------------------------------------------------- explorer queries
    def get_richlist(self, top_n=20):
        balances = {}
        with self.lock:
            for v in self.utxo_set.values():
                balances[v["address"]] = balances.get(v["address"], 0) + v["amount"]
        return sorted(balances.items(), key=lambda x: -x[1])[:top_n]

    def get_supply(self) -> int:
        with self.lock:
            return sum(v["amount"] for v in self.utxo_set.values())

    def get_block_by_height(self, height: int):
        with self.lock:
            if 0 <= height < len(self.chain):
                return self.chain[height]
        return None

    def get_block_by_hash(self, h: str):
        with self.lock:
            for b in self.chain:
                if b.hash() == h:
                    return b
        return None

    def find_transaction(self, txid: str):
        with self.lock:
            for b in self.chain:
                for tx in b.transactions:
                    if tx.txid == txid:
                        return tx, b.height
            if txid in self.mempool:
                return self.mempool[txid], None
        return None, None
