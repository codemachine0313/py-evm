from evm.chains.mainnet.constants import (
    DAO_FORK_BLOCK_NUMBER
)
from evm.vm.forks.frontier import FrontierVM

from .blocks import HomesteadBlock
from .computation import HomesteadComputation
from .validation import validate_homestead_transaction
from .headers import (
    create_homestead_header_from_parent,
    configure_homestead_header,
)
from .vm_state import HomesteadVMState


class MetaHomesteadVM(FrontierVM):
    support_dao_fork = True
    dao_fork_block_number = DAO_FORK_BLOCK_NUMBER


HomesteadVM = MetaHomesteadVM.configure(
    name='HomesteadVM',
    # classes
    _block_class=HomesteadBlock,
    _computation_class=HomesteadComputation,
    _state_class=HomesteadVMState,
    # method overrides
    validate_transaction=validate_homestead_transaction,
    create_header_from_parent=staticmethod(create_homestead_header_from_parent),
    configure_header=configure_homestead_header,
    # mode
    _is_stateless=True,
)
