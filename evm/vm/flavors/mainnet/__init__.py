from evm import constants
from evm import Chain

from evm.vm.flavors import (
    EIP150VM,
    FrontierVM,
    HomesteadVM,
)


MainnetEVM = Chain.configure(
    'MainnetEVM',
    vm_configuration=(
        (0, FrontierVM),
        (constants.HOMESTEAD_MAINNET_BLOCK, HomesteadVM),
        (constants.EIP150_MAINNET_BLOCK, EIP150VM)
    )
)
