import json
import socket
import threading
import time


class P2PNode:
    """
    Minimal gossip-based P2P layer: peers exchange newline-delimited JSON
    messages over plain TCP. Supports NEW_BLOCK / NEW_TX broadcast and
    GET_CHAIN longest-chain sync -- the essential primitives real P2P
    networks (Bitcoin/Ravencoin included) are built from, without the
    binary wire-protocol overhead that isn't needed for this reference node.
    """

    def __init__(self, blockchain, host="0.0.0.0", port=8767, peers=None):
        self.blockchain = blockchain
        self.host = host
        self.port = port
        self.peers = set(peers or [])
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._sync_loop, daemon=True).start()

    def stop(self):
        self.running = False

    def _listen(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen(20)
        srv.settimeout(1.0)
        while self.running:
            try:
                conn, _addr = srv.accept()
                threading.Thread(target=self._handle_conn, args=(conn,), daemon=True).start()
            except socket.timeout:
                continue
            except OSError:
                break
        srv.close()

    def _handle_conn(self, conn):
        try:
            data = b""
            conn.settimeout(5)
            while True:
                chunk = conn.recv(1 << 20)
                if not chunk:
                    break
                data += chunk
                if data.endswith(b"\n"):
                    break
            if data:
                self._handle_message(json.loads(data.decode()), conn)
        except Exception:
            pass
        finally:
            conn.close()

    def _handle_message(self, msg, conn):
        from core.block import Block
        from core.transaction import Transaction

        mtype = msg.get("type")
        if mtype == "PING":
            self._reply(conn, {"type": "PONG"})
        elif mtype == "NEW_BLOCK":
            self.blockchain.add_block(Block.from_dict(msg["block"]))
        elif mtype == "NEW_TX":
            self.blockchain.add_transaction_to_mempool(Transaction.from_dict(msg["tx"]))
        elif mtype == "GET_CHAIN":
            self._reply(conn, {"type": "CHAIN", "chain": [b.to_dict() for b in self.blockchain.chain]})
        elif mtype == "GET_PEERS":
            self._reply(conn, {"type": "PEERS", "peers": list(self.peers)})

    def _reply(self, conn, msg):
        try:
            conn.sendall((json.dumps(msg) + "\n").encode())
        except Exception:
            pass

    def _send_to_peer(self, peer, msg, expect_reply=False, timeout=3):
        try:
            host, port = peer.split(":")
            with socket.create_connection((host, int(port)), timeout=timeout) as s:
                s.sendall((json.dumps(msg) + "\n").encode())
                if expect_reply:
                    s.settimeout(timeout)
                    data = b""
                    while True:
                        chunk = s.recv(1 << 20)
                        if not chunk:
                            break
                        data += chunk
                        if data.endswith(b"\n"):
                            break
                    return json.loads(data.decode()) if data else None
        except Exception:
            return None
        return None

    def broadcast_block(self, block):
        for peer in list(self.peers):
            self._send_to_peer(peer, {"type": "NEW_BLOCK", "block": block.to_dict()})

    def broadcast_transaction(self, tx):
        for peer in list(self.peers):
            self._send_to_peer(peer, {"type": "NEW_TX", "tx": tx.to_dict()})

    def add_peer(self, peer: str):
        self.peers.add(peer)

    def _sync_loop(self):
        from core.block import Block

        while self.running:
            time.sleep(15)
            for peer in list(self.peers):
                resp = self._send_to_peer(peer, {"type": "GET_CHAIN"}, expect_reply=True)
                if not resp or resp.get("type") != "CHAIN":
                    continue
                remote_chain = resp["chain"]
                if len(remote_chain) > len(self.blockchain.chain):
                    with self.blockchain.lock:
                        for i in range(len(self.blockchain.chain), len(remote_chain)):
                            ok, _reason = self.blockchain.add_block(Block.from_dict(remote_chain[i]))
                            if not ok:
                                break
