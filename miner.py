import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.pow import yrc_hash, hash_meets_target  # noqa: E402
from core.block import Block  # noqa: E402


def mine_block(block: Block, max_attempts=None):
    """In-process mining loop. Mutates block.header.nonce until PoW target is met."""
    header = block.header
    nonce = 0
    while True:
        header.nonce = nonce
        if hash_meets_target(yrc_hash(header.serialize()), header.bits):
            return block
        nonce += 1
        if max_attempts and nonce > max_attempts:
            return None


def remote_mine(rpc_url: str, address: str, rounds: int = 0):
    """
    Standalone CPU miner that talks to a running node purely over JSON-RPC
    (getblocktemplate / submitblock) -- the same role XMRig/SRBMiner/Rigel/
    lolMiner play against a KAWPOW node, just using YRC-Hash instead.
    """
    import requests

    session = requests.Session()
    count = 0
    while rounds == 0 or count < rounds:
        tpl = session.post(rpc_url, json={"jsonrpc": "2.0", "method": "getblocktemplate", "params": [address], "id": 1}).json()
        if "result" not in tpl or tpl["result"] is None:
            print("[miner] failed to fetch template, retrying...")
            time.sleep(2)
            continue
        block = Block.from_dict(tpl["result"])
        target = block.header.bits
        start = time.time()
        mined = mine_block(block)
        elapsed = time.time() - start
        if mined:
            hashes_tried = mined.header.nonce + 1
            hashrate = hashes_tried / elapsed if elapsed > 0 else 0
            resp = session.post(
                rpc_url, json={"jsonrpc": "2.0", "method": "submitblock", "params": [mined.to_dict()], "id": 2}
            ).json()
            print(f"[miner] block {mined.height} found in {elapsed:.2f}s "
                  f"({hashrate:.1f} H/s, nonce={mined.header.nonce}) -> {resp.get('result')}")
        count += 1


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="YourCoin reference CPU miner (YRC-Hash)")
    p.add_argument("--rpc", default="http://127.0.0.1:8766/rpc")
    p.add_argument("--address", required=True, help="YRC address to receive mining rewards")
    p.add_argument("--rounds", type=int, default=0, help="0 = mine forever")
    args = p.parse_args()
    remote_mine(args.rpc, args.address, args.rounds)
