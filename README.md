# yourcoin
this is secure &amp; encrypted, open source crypto mining software ⛏️

YourCoin (YRC)
A complete, working proof-of-work cryptocurrency: real ECDSA wallets, a UTXO ledger, memory-hard (ASIC-resistant) mining, P2P networking, JSON-RPC + REST APIs, a block explorer, a CLI wallet, a standalone miner, and a Stratum-style mining pool server. MIT licensed.
What this actually is (please read before mainnet-launching anything)
This is an original, from-scratch Python implementation, not a patched fork of Ravencoin/Bitcoin's C++ codebase. The earlier architecture document recommended forking Ravencoin Core because that's the correct call for a real production launch — but doing that requires cloning and compiling a multi-gigabyte C++ project, which isn't possible in an offline sandbox. What you have here instead is fully functional, tested, running software that implements every piece of that architecture (consensus, ledger, wallet, P2P, mining, pool, explorer, APIs) in readable Python, so you can run it today on a Termux/Android box, understand every line, and treat it as either:
A real, working small-scale PoW coin as-is, or
A reference implementation / testbed while a C++ port (using the actual Ravencoin codebase, per the earlier document) is built for real mainnet scale and GPU-mineable KAWPOW.
Proof-of-work algorithm: YRC-Hash = SHA256(scrypt(header, N=1024)). This is a genuine memory-hard, ASIC-resistant PoW function (same family as Litecoin's scrypt) — not a placeholder. It is CPU-mineable out of the box. Wiring in real KAWPOW/ProgPoW (GPU, DAG-based) would mean replacing core/pow.py with an OpenCL/CUDA kernel binding; the rest of the system (blocks, transactions, RPC, pool) is written against a swappable yrc_hash(header) -> 32 bytes interface specifically so that swap is localized to one file.
Seed phrases use a custom 12-word scheme (entropy + checksum, same structure as BIP39) with a procedurally generated wordlist, since bundling the official BIP39 wordlist wasn't possible offline. Not interoperable with BIP39 wallets, but fully functional and equally secure.
Quickstart
pip install -r requirements.txt   # flask, requests, cryptography

# 1. Start a node (creates genesis block + data dir on first run)
python3 node.py --network devnet

# 2. In another terminal: create a wallet and see your address
python3 cli/wallet_cli.py --network devnet address

# 3. Mine some coins to yourself (built-in miner, like `generate` in early Bitcoin)
curl -X POST http://127.0.0.1:28766/rpc -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"generatetoaddress","params":[5,"<your-address>"],"id":1}'

# 4. Check your balance
python3 cli/wallet_cli.py --network devnet balance

# 5. Send coins to someone else
python3 cli/wallet_cli.py --network devnet send <their-address> 10.5

# 6. Open the block explorer in a browser
http://127.0.0.1:28766/
Networks: --network mainnet|testnet|devnet (each has its own genesis block, address prefix, magic bytes, and default ports — see config.py).
Standalone mining (separate process, like a real miner binary)
python3 miner/miner.py --rpc http://127.0.0.1:28766/rpc --address <your-address> --rounds 0
Mining pool (Stratum protocol)
python3 pool/stratum_server.py --rpc http://127.0.0.1:28766/rpc --address <pool-payout-address> --port 3333
Speaks real mining.subscribe / mining.authorize / mining.notify / mining.submit Stratum messages over TCP, with pool-difficulty shares and automatic full-block submission when a share also solves the block.
Running two peered nodes (P2P test)
python3 node.py --network devnet --p2pport 28767 --rpcport 28766 --datadir ./data/nodeA
python3 node.py --network devnet --p2pport 28768 --rpcport 28769 --peer 127.0.0.1:28767 --datadir ./data/nodeB
Node B will pull node A's chain via GET_CHAIN sync (runs every 15s) and receive live NEW_BLOCK/NEW_TX gossip once connected.
Docker
docker compose up -d --build
Project layout
config.py           network parameters (genesis, ports, address prefixes, reward schedule)
core/
  base58.py          Base58Check (from scratch)
  crypto_utils.py     SECP256K1 sign/verify (built on `cryptography`)
  pow.py              YRC-Hash proof-of-work function
  transaction.py      UTXO transaction model + signing/verification
  block.py            Block/BlockHeader + merkle tree
  blockchain.py        the chain: validation, UTXO set, difficulty, persistence
wallet/
  mnemonic_yrc.py      BIP39-style seed phrases (custom wordlist)
  wallet.py            key derivation, addresses, WIF export, tx building
network/p2p.py          gossip P2P node
api/app.py              JSON-RPC 2.0 + REST + HTML explorer (Flask)
explorer/templates/      explorer UI
miner/miner.py           CPU miner (in-process + standalone RPC client)
pool/stratum_server.py   Stratum-protocol pool server
cli/wallet_cli.py        CLI wallet
node.py                  main entrypoint
API reference (quick)
JSON-RPC — POST /rpc {"jsonrpc":"2.0","method":"...","params":[...],"id":1} getblockchaininfo, getblockcount, getblockhash, getblock, getbalance, listunspent, gettransaction, sendrawtransaction, getblocktemplate, submitblock, generatetoaddress, getmininginfo, getpeerinfo, validateaddress, getnetworkinfo.
REST — GET /rest/chaininfo, /rest/block/<height_or_hash>, /rest/tx/<txid>, /rest/address/<addr>, /rest/richlist, /rest/supply, /rest/mining-stats.
Explorer (HTML) — /, /explorer/block/<h>, /explorer/address/<addr>, /explorer/richlist.
Security properties actually implemented (and tested)
Real ECDSA (SECP256K1) signing/verification per transaction input.
Double-spend protection: UTXO lookup + in-batch spent-set tracking, both at mempool-admission time and at block-validation time.
Tampered-signature transactions are rejected before entering the mempool.
Deterministic genesis block across independent nodes (required for any multi-node network to agree on a starting point).
Difficulty retargets every block (DGW-style rolling window), clamped to ±4x per adjustment to resist hashrate-swing attacks.
Dust/anti-spam floor on transaction outputs and minimum relay fee.
Address format validated before any coinbase reward is paid out.
What would still need to happen before a real public mainnet launch
Independent security review of this codebase (it's new code, unlike a Ravencoin fork which inherits years of audited history).
Replace core/pow.py with real KAWPOW if GPU-scale ASIC resistance and compatibility with XMRig/SRBMiner/Rigel/lolMiner binaries is required — this Python scrypt-based PoW is CPU-only and not compatible with those miner binaries as-is.
A binary P2P wire protocol and NAT traversal/UPnP for real internet-scale peer discovery (this reference P2P layer is plain-TCP/JSON, fine on a LAN or between servers with open ports, not a production gossip network).
Legal/regulatory review (see the earlier architecture document).