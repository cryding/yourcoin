import os

from flask import Flask, request, jsonify, render_template

import config
from core.block import Block
from core.transaction import Transaction


def create_app(blockchain, p2p, network):
    template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "explorer", "templates")
    app = Flask(__name__, template_folder=template_dir)

    # ================= JSON-RPC 2.0 =================
    def dispatch_rpc(method, params):
        params = params or []
        if method == "getblockchaininfo":
            return {
                "chain": network,
                "blocks": len(blockchain.chain) - 1,
                "bestblockhash": blockchain.chain[-1].hash(),
                "difficulty_target": blockchain.current_target(),
                "supply": blockchain.get_supply(),
                "max_supply": config.MAX_SUPPLY,
            }
        if method == "getblockcount":
            return len(blockchain.chain) - 1
        if method == "getblockhash":
            b = blockchain.get_block_by_height(params[0])
            return b.hash() if b else None
        if method == "getblock":
            b = blockchain.get_block_by_hash(params[0])
            if b is None:
                try:
                    b = blockchain.get_block_by_height(int(params[0]))
                except ValueError:
                    b = None
            return b.to_dict() if b else None
        if method == "getbalance":
            return blockchain.get_balance(params[0]) / config.COIN
        if method == "listunspent":
            return blockchain.get_utxos_for_address(params[0])
        if method == "gettransaction":
            tx, height = blockchain.find_transaction(params[0])
            if not tx:
                return None
            d = tx.to_dict()
            d["confirmed_height"] = height
            return d
        if method == "sendrawtransaction":
            tx = Transaction.from_dict(params[0])
            ok, reason = blockchain.add_transaction_to_mempool(tx)
            if ok and p2p:
                p2p.broadcast_transaction(tx)
            return {"accepted": ok, "reason": reason, "txid": tx.txid}
        if method == "getblocktemplate":
            return blockchain.create_block_template(params[0]).to_dict()
        if method == "submitblock":
            block = Block.from_dict(params[0])
            ok, reason = blockchain.add_block(block)
            if ok and p2p:
                p2p.broadcast_block(block)
            return {"accepted": ok, "reason": reason}
        if method == "generatetoaddress":
            n, address = params[0], params[1]
            from miner.miner import mine_block
            found = []
            for _ in range(n):
                block = blockchain.create_block_template(address)
                mined = mine_block(block)
                ok, reason = blockchain.add_block(mined)
                if ok:
                    found.append(mined.hash())
                    if p2p:
                        p2p.broadcast_block(mined)
                else:
                    break
            return found
        if method == "getmininginfo":
            return {
                "blocks": len(blockchain.chain) - 1,
                "difficulty_target": blockchain.current_target(),
                "block_reward": blockchain.block_reward(len(blockchain.chain)) / config.COIN,
                "mempool_size": len(blockchain.mempool),
            }
        if method == "getpeerinfo":
            return list(p2p.peers) if p2p else []
        if method == "validateaddress":
            from wallet.wallet import validate_address
            return {"isvalid": validate_address(params[0], network), "address": params[0]}
        if method == "getnetworkinfo":
            return {"network": network, "p2p_port": p2p.port if p2p else None, "peers": len(p2p.peers) if p2p else 0}
        raise ValueError(f"unknown method: {method}")

    @app.route("/rpc", methods=["POST"])
    def rpc():
        req = request.get_json(force=True)
        req_id = req.get("id")
        try:
            result = dispatch_rpc(req.get("method"), req.get("params", []))
            return jsonify({"jsonrpc": "2.0", "result": result, "id": req_id})
        except Exception as e:
            return jsonify({"jsonrpc": "2.0", "error": str(e), "id": req_id}), 400

    # ================= REST API (explorer-facing) =================
    @app.route("/rest/chaininfo")
    def rest_chaininfo():
        return jsonify(dispatch_rpc("getblockchaininfo", []))

    @app.route("/rest/block/<h>")
    def rest_block(h):
        b = blockchain.get_block_by_hash(h)
        if b is None:
            try:
                b = blockchain.get_block_by_height(int(h))
            except ValueError:
                b = None
        return jsonify(b.to_dict() if b else {"error": "not found"}), (200 if b else 404)

    @app.route("/rest/tx/<txid>")
    def rest_tx(txid):
        result = dispatch_rpc("gettransaction", [txid])
        return jsonify(result if result else {"error": "not found"}), (200 if result else 404)

    @app.route("/rest/address/<addr>")
    def rest_address(addr):
        return jsonify({
            "address": addr,
            "balance": blockchain.get_balance(addr) / config.COIN,
            "utxo_count": len(blockchain.get_utxos_for_address(addr)),
            "utxos": blockchain.get_utxos_for_address(addr),
        })

    @app.route("/rest/richlist")
    def rest_richlist():
        return jsonify([{"address": a, "balance": bal / config.COIN} for a, bal in blockchain.get_richlist(20)])

    @app.route("/rest/supply")
    def rest_supply():
        return jsonify({
            "circulating_supply": blockchain.get_supply() / config.COIN,
            "max_supply": config.MAX_SUPPLY / config.COIN,
            "percent_mined": round(100 * blockchain.get_supply() / config.MAX_SUPPLY, 6),
        })

    @app.route("/rest/mining-stats")
    def rest_mining_stats():
        height = len(blockchain.chain) - 1
        return jsonify({
            "height": height,
            "difficulty_target": blockchain.current_target(),
            "block_reward": blockchain.block_reward(height + 1) / config.COIN,
            "mempool_size": len(blockchain.mempool),
        })

    # ================= Wallet convenience (non-custodial: sign client-side) =================
    @app.route("/wallet/info")
    def wallet_info():
        return jsonify({
            "note": "This node does not custody private keys. Use the CLI wallet (cli/wallet_cli.py), "
                    "desktop wallet, or web wallet to sign transactions locally, then submit via "
                    "POST /rpc {method: sendrawtransaction}."
        })

    # ================= HTML Explorer =================
    @app.route("/")
    def explorer_home():
        blocks = list(reversed(blockchain.chain[-10:]))
        return render_template(
            "index.html",
            blocks=blocks,
            height=len(blockchain.chain) - 1,
            supply=blockchain.get_supply() / config.COIN,
            max_supply=config.MAX_SUPPLY / config.COIN,
            network=network,
            mempool_size=len(blockchain.mempool),
        )

    @app.route("/explorer/block/<h>")
    def explorer_block(h):
        b = blockchain.get_block_by_hash(h)
        if b is None:
            try:
                b = blockchain.get_block_by_height(int(h))
            except ValueError:
                b = None
        return render_template("block.html", block=b)

    @app.route("/explorer/address/<addr>")
    def explorer_address(addr):
        return render_template(
            "address.html",
            address=addr,
            balance=blockchain.get_balance(addr) / config.COIN,
            utxos=blockchain.get_utxos_for_address(addr),
        )

    @app.route("/explorer/richlist")
    def explorer_richlist():
        return render_template("richlist.html", richlist=[(a, b / config.COIN) for a, b in blockchain.get_richlist(50)])

    return app
