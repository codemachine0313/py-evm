from hashlib import sha256

from evm import constants

from evm.utils.address import (
    force_bytes_to_address,
)
from evm.utils.numeric import (
    ceil32,
)


def precompiled_sha256(computation):
    word_count = ceil32(computation.message.data) // 32
    gas_fee = constants.GAS_SHA256 + word_count * constants.GAS_SHA256WORD

    computation.gas_meter.consume_gas(gas_fee, reason="SHA256 Precompile")
    input_bytes = computation.message.data
    hash = sha256(input_bytes).digest()
    computation.output = hash
    return computation


def not_implemented(name):
    def inner(computation):
        raise NotImplementedError("Precompile {0} is not implemented".format(name))
    return inner


PRECOMPILES = {
    force_bytes_to_address(b'\x01'): not_implemented('ecrecover'),
    force_bytes_to_address(b'\x02'): precompiled_sha256,
    force_bytes_to_address(b'\x03'): not_implemented('ripemd160'),
    force_bytes_to_address(b'\x04'): not_implemented('identity'),
}


"""
def proc_ecrecover(ext, msg):
    # print('ecrecover proc', msg.gas)
    OP_GAS = opcodes.GECRECOVER
    gas_cost = OP_GAS
    if msg.gas < gas_cost:
        return 0, 0, []

    message_hash_bytes = [0] * 32
    msg.data.extract_copy(message_hash_bytes, 0, 0, 32)
    message_hash = b''.join(map(ascii_chr, message_hash_bytes))

    # TODO: This conversion isn't really necessary.
    # TODO: Invesitage if the check below is really needed.
    v = msg.data.extract32(32)
    r = msg.data.extract32(64)
    s = msg.data.extract32(96)

    if r >= bitcoin.N or s >= bitcoin.N or v < 27 or v > 28:
        return 1, msg.gas - opcodes.GECRECOVER, []

    signature_bytes = [0] * 64
    msg.data.extract_copy(signature_bytes, 0, 64, 32)
    msg.data.extract_copy(signature_bytes, 32, 96, 32)
    signature = b''.join(map(ascii_chr, signature_bytes))

    pk = PublicKey(flags=ALL_FLAGS)
    try:
        pk.public_key = pk.ecdsa_recover(
            message_hash,
            pk.ecdsa_recoverable_deserialize(
                signature,
                v - 27
            ),
            raw=True
        )
    except Exception:
        # Recovery failed
        return 1, msg.gas - gas_cost, []

    pub = pk.serialize(compressed=False)
    o = [0] * 12 + [safe_ord(x) for x in utils.sha3(pub[1:])[-20:]]
    return 1, msg.gas - gas_cost, o


def proc_ripemd160(ext, msg):
    # print('ripemd160 proc', msg.gas)
    OP_GAS = opcodes.GRIPEMD160BASE + \
        (utils.ceil32(msg.data.size) // 32) * opcodes.GRIPEMD160WORD

    gas_cost = constants.GAS_SHA256
    if msg.gas < gas_cost:
        return 0, 0, []
    d = msg.data.extract_all()
    o = [0] * 12 + [safe_ord(x) for x in bitcoin.ripemd.RIPEMD160(d).digest()]
    return 1, msg.gas - gas_cost, o


def proc_identity(ext, msg):
    #print('identity proc', msg.gas)
    OP_GAS = opcodes.GIDENTITYBASE + \
        opcodes.GIDENTITYWORD * (utils.ceil32(msg.data.size) // 32)
    gas_cost = OP_GAS
    if msg.gas < gas_cost:
        return 0, 0, []
    o = [0] * msg.data.size
    msg.data.extract_copy(o, 0, 0, len(o))
    return 1, msg.gas - gas_cost, o
"""
