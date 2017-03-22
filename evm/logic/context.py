import logging

from eth_utils import (
    pad_right,
)

from evm import constants
from evm.exceptions import (
    OutOfGas,
)

from evm.utils.address import (
    force_bytes_to_address,
)
from evm.utils.numeric import (
    ceil32,
    big_endian_to_int,
    int_to_big_endian,
)


logger = logging.getLogger('evm.logic.context')


def address(computation):
    logger.info('CALLER: %s', computation.msg.account)
    computation.stack.push(computation.msg.account)


def caller(computation):
    logger.info('CALLER: %s', computation.msg.sender)
    computation.stack.push(computation.msg.sender)


def callvalue(computation):
    logger.info('CALLVALUE: %s', computation.msg.value)
    computation.stack.push(int_to_big_endian(computation.msg.value))


def calldataload(computation):
    """
    Load call data into memory.
    """
    start_position = big_endian_to_int(computation.stack.pop())

    value = computation.msg.data[start_position:start_position + 32]
    padded_value = pad_right(value, 32, b'\x00')
    normalized_value = padded_value.lstrip(b'\x00')

    logger.info(
        'CALLDATALOAD: [%s:%s] -> %s',
        start_position,
        start_position + 32,
        normalized_value,
    )
    computation.stack.push(normalized_value)


def codecopy(computation):
    mem_start_position = big_endian_to_int(computation.stack.pop())
    code_start_position = big_endian_to_int(computation.stack.pop())
    size = big_endian_to_int(computation.stack.pop())

    computation.extend_memory(mem_start_position, size)

    word_count = ceil32(size) // 32
    copy_gas_cost = constants.GAS_COPY * word_count

    computation.gas_meter.consume_gas(copy_gas_cost)
    if computation.gas_meter.is_out_of_gas:
        raise OutOfGas("Insufficient gas to copy data")

    with computation.code.seek(code_start_position):
        code_bytes = computation.code.read(size)

    padded_code_bytes = pad_right(code_bytes, size, b'\x00')

    computation.memory.write(mem_start_position, size, padded_code_bytes)

    logger.info(
        "CODECOPY: [%s, %s] -> %s",
        code_start_position,
        code_start_position + size,
        padded_code_bytes,
    )


def calldatacopy(computation):
    mem_start_position = big_endian_to_int(computation.stack.pop())
    calldata_start_position = big_endian_to_int(computation.stack.pop())
    size = big_endian_to_int(computation.stack.pop())

    computation.extend_memory(mem_start_position, size)

    value = computation.msg.data[calldata_start_position: calldata_start_position + size]
    padded_value = pad_right(value, size, b'\x00')

    computation.memory.write(mem_start_position, size, padded_value)

    logger.info(
        "CALLDATACOPY: [%s: %s] -> %s",
        calldata_start_position,
        calldata_start_position + size,
        padded_value,
    )


def extcodesize(computation):
    account = force_bytes_to_address(computation.stack.pop())
    code_size = len(computation.storage.get_code(account))

    logger.info('EXTCODESIZE: %s', code_size)

    computation.stack.push(int_to_big_endian(code_size))


def extcodecopy(computation):
    account = force_bytes_to_address(computation.stack.pop())
    mem_start_position = big_endian_to_int(computation.stack.pop())
    code_start_position = big_endian_to_int(computation.stack.pop())
    size = big_endian_to_int(computation.stack.pop())

    computation.extend_memory(mem_start_position, size)

    word_count = ceil32(size) // 32
    copy_gas_cost = constants.GAS_COPY * word_count

    computation.gas_meter.consume_gas(copy_gas_cost)
    if computation.gas_meter.is_out_of_gas:
        raise OutOfGas("Insufficient gas to copy data")

    code = computation.storage.get_code(account)
    code_bytes = code[code_start_position:code_start_position + size]
    padded_code_bytes = pad_right(code_bytes, size, b'\x00')

    computation.memory.write(mem_start_position, size, padded_code_bytes)

    logger.info(
        'EXTCODECOPY: [%s:%s] -> %s',
        code_start_position,
        code_start_position + code_size,
        padded_code_bytes,
    )
