import copy

from evm import constants
from evm import opcode_values
from evm import mnemonics

from evm.opcode import as_opcode

from evm.logic import (
    call,
    context,
    storage,
    system,
)

from evm.vm.flavors.homestead.opcodes import HOMESTEAD_OPCODES


UPDATED_OPCODES = {
    opcode_values.EXTCODESIZE: as_opcode(
        logic_fn=context.extcodesize,
        mnemonic=mnemonics.EXTCODESIZE,
        gas_cost=constants.GAS_EXTCODE_EIP150,
    ),
    opcode_values.EXTCODECOPY: as_opcode(
        logic_fn=context.extcodecopy,
        mnemonic=mnemonics.EXTCODECOPY,
        gas_cost=constants.GAS_EXTCODE_EIP150,
    ),
    opcode_values.BALANCE: as_opcode(
        logic_fn=context.balance,
        mnemonic=mnemonics.BALANCE,
        gas_cost=constants.GAS_BALANCE_EIP150,
    ),
    opcode_values.SLOAD: as_opcode(
        logic_fn=storage.sload,
        mnemonic=mnemonics.SLOAD,
        gas_cost=constants.GAS_SLOAD_EIP150,
    ),
    opcode_values.SUICIDE: as_opcode(
        logic_fn=system.suicide_eip150,
        mnemonic=mnemonics.SUICIDE,
        gas_cost=constants.GAS_SUICIDE_EIP150,
    ),
    opcode_values.CREATE: system.CreateEIP150.configure(
        name='opcode:CREATE',
        mnemonic=mnemonics.CREATE,
        gas_cost=constants.GAS_CREATE,
    )(),
    opcode_values.CALL: call.CallEIP150.configure(
        name='opcode:CALL',
        mnemonic=mnemonics.CALL,
        gas_cost=constants.GAS_CALL_EIP150,
    )(),
    opcode_values.CALLCODE: call.CallCodeEIP150.configure(
        name='opcode:CALLCODE',
        mnemonic=mnemonics.CALLCODE,
        gas_cost=constants.GAS_CALL_EIP150,
    )(),
    opcode_values.DELEGATECALL: call.DelegateCallEIP150.configure(
        name='opcode:DELEGATECALL',
        mnemonic=mnemonics.DELEGATECALL,
        gas_cost=constants.GAS_CALL_EIP150,
    )(),
}


EIP150_OPCODES = {
    **copy.deepcopy(HOMESTEAD_OPCODES),  # noqa: E999
    **UPDATED_OPCODES,
}
