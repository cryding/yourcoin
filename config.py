"""
YourCoin (YRC) chain configuration.
"""

COIN = 100_000_000                     # 1 YRC = 100,000,000 base units (like satoshis)
INITIAL_REWARD = 5000 * COIN           # block reward at height 0
HALVING_INTERVAL = 2_100_000           # blocks between halvings
MAX_SUPPLY = 21_000_000_000 * COIN     # hard cap
BLOCK_TIME_TARGET = 60                 # seconds, target time between blocks
DIFFICULTY_WINDOW = 24                 # rolling window for dynamic difficulty (DGW-style)
MIN_RELAY_FEE = 1000                   # base units, anti-spam floor
DUST_THRESHOLD = 5460                  # outputs below this are rejected (anti-spam)

GENESIS_MESSAGE = "YourCoin Genesis - Financial Freedom Through Proof of Work"
GENESIS_TIMESTAMP = 1735689600         # 2025-01-01T00:00:00Z
GENESIS_BURN_ADDRESS_PLACEHOLDER = "unspendable-genesis-output"

# Address version bytes -- must differ across networks to prevent address confusion
ADDRESS_PREFIX = {
    "mainnet": b"\x3c",   # produces addresses that look distinct from BTC/RVN
    "testnet": b"\x7c",
    "devnet": b"\x8c",
}

# WIF (private key export) version bytes -- independent from address prefixes
# so no arithmetic overflow risk, and each network's WIF keys are visually distinct.
WIF_PREFIX = {
    "mainnet": b"\xb0",
    "testnet": b"\xef",
    "devnet": b"\xf0",
}

# P2P network magic bytes -- prevents cross-network peer handshakes
MAGIC_BYTES = {
    "mainnet": b"YRC1",
    "testnet": b"YRCT",
    "devnet": b"YRCD",
}

DEFAULT_P2P_PORTS = {"mainnet": 8767, "testnet": 18767, "devnet": 28767}
RPC_PORTS = {"mainnet": 8766, "testnet": 18766, "devnet": 28766}

# Easy demo-scale genesis target (top byte must be zero). A real mainnet launch
# would tune this + the retarget window to match actual expected network hashrate.
GENESIS_TARGET = (2 ** 256 - 1) >> 8
MAX_TARGET = (2 ** 256 - 1) >> 1
