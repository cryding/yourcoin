import json
import os
import socket
import sys
import threading
import time

import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.pow import yrc_hash, hash_meets_target  # noqa: E402
from core.block import Block  # noqa: E402


class StratumPool:
    """
    Reference Stratum-protocol-style pool server:
      - mining.subscribe / mining.authorize / mining.notify / mining.submit
      - PPLNS-style share accounting (simplified: raw share counts per worker;
        a production deployment would use Mining-Core/YiiMP directly, as
        documented in the architecture doc, for time-weighted PPLNS windows,
        payout batching, and a stats frontend)
      - pool difficulty is an easier sub-target of the real block target, so
        workers submit frequent shares while only rare shares are also valid
        full blocks, submitted to the node automatically.
    """

    def __init__(self, rpc_url, pool_address, host="0.0.0.0", port=3333, pool_diff_divisor=100):
        self.rpc_url = rpc_url
        self.pool_address = pool_address
        self.host, self.port = host, port
        self.pool_diff_divisor = pool_diff_divisor
        self.shares = {}  # worker -> share count (this round)
        self.blocks_found = 0
        self.current_template = None
        self.lock = threading.Lock()

    def rpc(self, method, params=None):
        r = requests.post(self.rpc_url, json={"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1}, timeout=10)
        return r.json().get("result")

    def refresh_template(self):
        tpl = self.rpc("getblocktemplate", [self.pool_address])
        if tpl:
            with self.lock:
                self.current_template = Block.from_dict(tpl)

    def start(self):
        self.refresh_template()
        threading.Thread(target=self._refresh_loop, daemon=True).start()
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen(50)
        print(f"[pool] stratum listening on {self.host}:{self.port}, paying out to {self.pool_address}")
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=self._handle_miner, args=(conn, addr), daemon=True).start()

    def _refresh_loop(self):
        while True:
            time.sleep(5)
            self.refresh_template()

    def _handle_miner(self, conn, addr):
        worker = f"{addr[0]}:{addr[1]}"
        buf = b""
        try:
            conn.settimeout(120)
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    self._handle_line(conn, line, worker)
        except Exception:
            pass
        finally:
            conn.close()

    def _handle_line(self, conn, line, default_worker):
        msg = json.loads(line.decode())
        method = msg.get("method")
        if method == "mining.subscribe":
            self._send(conn, {"id": msg.get("id"), "result": ["subscribed", "yourcoin-stratum-v1"], "error": None})
        elif method == "mining.authorize":
            worker = msg["params"][0]
            self.shares.setdefault(worker, 0)
            self._send(conn, {"id": msg.get("id"), "result": True, "error": None})
            self._send_job(conn)
        elif method == "mining.submit":
            worker, _job_id, nonce = msg["params"][0], msg["params"][1], int(msg["params"][2])
            accepted, found_block = self._process_share(worker, nonce)
            self._send(conn, {"id": msg.get("id"), "result": accepted, "error": None if accepted else "low-difficulty-share"})
        else:
            self._send(conn, {"id": msg.get("id"), "result": None, "error": "unknown method"})

    def _send_job(self, conn):
        with self.lock:
            h = self.current_template.header
            job = {"method": "mining.notify", "params": ["job1", h.prev_hash, h.merkle_root, h.timestamp, h.bits]}
        self._send(conn, job)

    def _process_share(self, worker, nonce):
        with self.lock:
            block = self.current_template
            block.header.nonce = nonce
            digest = yrc_hash(block.header.serialize())
            pool_target = min(block.header.bits * self.pool_diff_divisor, (2 ** 256) - 1)
            if not hash_meets_target(digest, pool_target):
                return False, False
            self.shares[worker] = self.shares.get(worker, 0) + 1
            if hash_meets_target(digest, block.header.bits):
                result = self.rpc("submitblock", [block.to_dict()])
                self.blocks_found += 1
                print(f"[pool] *** BLOCK FOUND by {worker} *** -> {result}")
                self.shares = {}  # new PPLNS round starts
                self.refresh_template()
                return True, True
            return True, False

    def _send(self, conn, msg):
        try:
            conn.sendall((json.dumps(msg) + "\n").encode())
        except Exception:
            pass


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="YourCoin reference Stratum mining pool")
    p.add_argument("--rpc", default="http://127.0.0.1:8766/rpc")
    p.add_argument("--address", required=True, help="pool payout wallet address")
    p.add_argument("--port", type=int, default=3333)
    args = p.parse_args()
    StratumPool(args.rpc, args.address, port=args.port).start()
