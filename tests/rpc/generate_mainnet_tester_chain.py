import os
import time

from eth_keys import (
    KeyAPI,
)

from eth_utils import (
    pad_left,
    int_to_big_endian,
    to_dict,
    to_tuple,
    to_wei,
)

from evm import MainnetTesterChain
from evm.db.backends.level import LevelDB
from evm.db.chain import BaseChainDB

# lifted from https://github.com/ethereum/eth-tester/blob/168c7a59/eth_tester/backends/pyevm/main.py

ZERO_ADDRESS = 20 * b'\x00'
ZERO_HASH32 = 32 * b'\x00'


EMPTY_RLP_LIST_HASH = b'\x1d\xccM\xe8\xde\xc7]z\xab\x85\xb5g\xb6\xcc\xd4\x1a\xd3\x12E\x1b\x94\x8at\x13\xf0\xa1B\xfd@\xd4\x93G'  # noqa: E501
BLANK_ROOT_HASH = b'V\xe8\x1f\x17\x1b\xccU\xa6\xff\x83E\xe6\x92\xc0\xf8n\x5bH\xe0\x1b\x99l\xad\xc0\x01b/\xb5\xe3c\xb4!'  # noqa: E501


GENESIS_BLOCK_NUMBER = 0
GENESIS_DIFFICULTY = 131072
GENESIS_GAS_LIMIT = 3141592
GENESIS_PARENT_HASH = ZERO_HASH32
GENESIS_COINBASE = ZERO_ADDRESS
GENESIS_NONCE = b'\x00\x00\x00\x00\x00\x00\x00*'  # 42 encoded as big-endian-integer
GENESIS_MIX_HASH = ZERO_HASH32
GENESIS_EXTRA_DATA = b''
GENESIS_INITIAL_ALLOC = {}


def get_default_account_state():
    return {
        'balance': to_wei(1000000, 'ether'),
        'storage': {},
        'code': b'',
        'nonce': 0,
    }


@to_tuple
def get_default_account_keys():
    keys = KeyAPI()

    for i in range(1, 11):
        pk_bytes = pad_left(int_to_big_endian(i), 32, b'\x00')
        private_key = keys.PrivateKey(pk_bytes)
        yield private_key


@to_dict
def generate_genesis_state(account_keys):
    for private_key in account_keys:
        account_state = get_default_account_state()
        yield private_key.public_key.to_canonical_address(), account_state


def get_default_genesis_params():
    genesis_params = {
        "bloom": 0,
        "coinbase": GENESIS_COINBASE,
        "difficulty": GENESIS_DIFFICULTY,
        "extra_data": GENESIS_EXTRA_DATA,
        "gas_limit": GENESIS_GAS_LIMIT,
        "gas_used": 0,
        "mix_hash": GENESIS_MIX_HASH,
        "nonce": GENESIS_NONCE,
        "block_number": GENESIS_BLOCK_NUMBER,
        "parent_hash": GENESIS_PARENT_HASH,
        "receipt_root": BLANK_ROOT_HASH,
        "timestamp": int(time.time()),
        "transaction_root": BLANK_ROOT_HASH,
        "uncles_hash": EMPTY_RLP_LIST_HASH
    }
    return genesis_params


def get_level_db(db_path):
    return BaseChainDB(LevelDB(db_path))


def setup_tester_chain(db_path, account_keys):
    db = get_level_db(db_path)

    genesis_params = get_default_genesis_params()
    genesis_state = generate_genesis_state(account_keys)

    chain = MainnetTesterChain.from_genesis(db, genesis_params, genesis_state)
    return chain


def build_chain(chain, account_keys):
    num_blocks = chain.get_block().number - 1
    if num_blocks < 1:
        key1 = account_keys[0]
        chain.mine_block(coinbase=key1.public_key.to_canonical_address())
    if num_blocks < 2:
        # mine 2nd block
        # note that the db folder is .gitignore, so some extra work is required to save the data
        #  - hacky short-term: remove from .gitignore, commit, then re-add to .gitignore
        #  - better long-term:
        #    - remove from .gitignore, then at beginning of test:
        #    - copy database to ignored folder
        #    - open database in ignored folder, then at end of test:
        #    - wipe ignored folder
        pass


if __name__ == '__main__':
    account_keys = get_default_account_keys()
    file_dir = os.path.dirname(os.path.realpath(__file__))
    db_path = os.path.join(file_dir, 'mainnet_tester_chain.db')
    if os.path.exists(db_path):
        chain = MainnetTesterChain(get_level_db(db_path))
    else:
        chain = setup_tester_chain(db_path, account_keys)
    build_chain(chain, account_keys)
