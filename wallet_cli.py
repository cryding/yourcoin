import argparse
import json
import os
import sys

import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from wallet.wallet import Wallet, build_transaction  # noqa: E402

WALLET_DIR = os.path.expanduser("~/.yourcoin")


def wallet_path(network):
    return os.path.join(WALLET_DIR, f"wallet_{network}.json")


def load_or_create_wallet(network) -> Wallet:
    os.makedirs(WALLET_DIR, exist_ok=True)
    path = wallet_path(network)
    if os.path.exists(path):
        with open(path) as f:
            d = json.load(f)
        return Wallet(network, mnemonic_phrase=d["mnemonic"])
    w = Wallet(network)
    with open(path, "w") as f:
        json.dump(w.to_dict(), f)
    os.chmod(path, 0o600)
    # Printed to stderr, not stdout: keeps `address`/`balance` command output
    # script-friendly (e.g. ADDR=$(wallet_cli.py address)) while still
    # surfacing the one-time seed phrase warning to the user's terminal.
    print("=" * 60, file=sys.stderr)
    print("NEW WALLET CREATED — WRITE DOWN YOUR SEED PHRASE NOW:", file=sys.stderr)
    print(w.mnemonic, file=sys.stderr)
    print("Anyone with this phrase can spend your funds. Store it offline.", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    return w


class RPCClient:
    def __init__(self, url):
        self.url = url

    def call(self, method, params=None):
        r = requests.post(self.url, json={"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1}, timeout=10)
        d = r.json()
        if d.get("error"):
            raise RuntimeError(d["error"])
        return d["result"]


class RemoteChainProxy:
    """Adapts the RPC client to the interface build_transaction() expects."""

    def __init__(self, rpc: RPCClient):
        self.rpc = rpc

    def get_utxos_for_address(self, address):
        return self.rpc.call("listunspent", [address])


def main():
    p = argparse.ArgumentParser(description="YourCoin (YRC) CLI Wallet")
    p.add_argument("--network", default="mainnet", choices=["mainnet", "testnet", "devnet"])
    p.add_argument("--rpc", default=None)
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("address", help="show your receive address")
    sub.add_parser("balance", help="show wallet balance")
    sub.add_parser("seed", help="show seed phrase (KEEP SECRET)")
    sub.add_parser("exportkey", help="export WIF private key (KEEP SECRET)")
    send_p = sub.add_parser("send", help="send YRC to an address")
    send_p.add_argument("to")
    send_p.add_argument("amount", type=float)
    send_p.add_argument("--fee", type=float, default=config.MIN_RELAY_FEE / config.COIN)
    args = p.parse_args()

    rpc_url = args.rpc or f"http://127.0.0.1:{config.RPC_PORTS[args.network]}/rpc"
    wallet = load_or_create_wallet(args.network)
    rpc = RPCClient(rpc_url)

    if args.cmd in (None, "address"):
        print(wallet.address)
    elif args.cmd == "balance":
        print(f"{rpc.call('getbalance', [wallet.address])} YRC")
    elif args.cmd == "seed":
        print(wallet.mnemonic or "(this wallet was imported from a private key — no seed phrase available)")
    elif args.cmd == "exportkey":
        print(wallet.export_private_key_wif())
    elif args.cmd == "send":
        proxy = RemoteChainProxy(rpc)
        tx = build_transaction(
            proxy, wallet, args.to, int(round(args.amount * config.COIN)), int(round(args.fee * config.COIN))
        )
        result = rpc.call("sendrawtransaction", [tx.to_dict()])
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
