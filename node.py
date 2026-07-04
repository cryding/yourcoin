import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
from core.blockchain import Blockchain  # noqa: E402
from network.p2p import P2PNode  # noqa: E402
from api.app import create_app  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="YourCoin (YRC) full node")
    p.add_argument("--network", choices=["mainnet", "testnet", "devnet"], default="mainnet")
    p.add_argument("--rpcport", type=int, default=None)
    p.add_argument("--p2pport", type=int, default=None)
    p.add_argument("--peer", action="append", default=[], help="host:port of a peer node, repeatable")
    p.add_argument("--datadir", default=None)
    args = p.parse_args()

    rpcport = args.rpcport or config.RPC_PORTS[args.network]
    p2pport = args.p2pport or config.DEFAULT_P2P_PORTS[args.network]

    blockchain = Blockchain(network=args.network, datadir=args.datadir)
    print(f"[node] network={args.network} height={len(blockchain.chain) - 1} "
          f"tip={blockchain.chain[-1].hash()[:16]}...")

    p2p = P2PNode(blockchain, port=p2pport, peers=args.peer)
    p2p.start()
    print(f"[node] P2P listening on 0.0.0.0:{p2pport} (peers: {list(p2p.peers) or 'none configured'})")

    app = create_app(blockchain, p2p, args.network)
    print(f"[node] RPC + REST + Explorer listening on 0.0.0.0:{rpcport}")
    app.run(host="0.0.0.0", port=rpcport, threaded=True)


if __name__ == "__main__":
    main()
