from evm import constants

from evm.utils.padding import (
    pad32,
)


def sstore(computation):
    slot, value = computation.stack.pop(num_items=2, type_hint=constants.BYTES)
    padded_slot = pad32(slot)

    current_value = computation.evm.block.state_db.get_storage(
        address=computation.msg.storage_address,
        slot=padded_slot,
    )

    is_currently_empty = not bool(current_value.strip(b'\x00'))
    is_going_to_be_empty = not bool(value.strip(b'\x00'))

    if is_currently_empty:
        gas_refund = 0
    elif is_going_to_be_empty:
        gas_refund = constants.REFUND_SCLEAR
    else:
        gas_refund = 0

    if is_currently_empty and is_going_to_be_empty:
        gas_cost = constants.GAS_SRESET
    elif is_currently_empty:
        gas_cost = constants.GAS_SSET
    elif is_going_to_be_empty:
        gas_cost = constants.GAS_SRESET
    else:
        gas_cost = constants.GAS_SRESET

    computation.gas_meter.consume_gas(gas_cost, reason="SSTORE: {0}[{1}] -> {2} ({3})".format(
        computation.msg.storage_address,
        slot,
        value,
        current_value,
    ))

    if gas_refund:
        computation.gas_meter.refund_gas(gas_refund)

    computation.evm.block.state_db.set_storage(
        address=computation.msg.storage_address,
        slot=padded_slot,
        value=value,
    )


def sload(computation):
    slot = computation.stack.pop(type_hint=constants.BYTES)
    padded_slot = pad32(slot)

    value = computation.evm.block.state_db.get_storage(
        address=computation.msg.storage_address,
        slot=padded_slot,
    )
    computation.stack.push(value)
