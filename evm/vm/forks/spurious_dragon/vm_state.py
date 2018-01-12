
from evm.utils.hexadecimal import (
    encode_hex,
)
from evm.vm.forks.frontier.vm_state import (
    _execute_frontier_transaction,
)
from evm.vm.forks.homestead.vm_state import (
    HomesteadVMState,
)
from .utils import collect_touched_accounts


class SpuriousDragonVMState(HomesteadVMState):
    def execute_transaction(self, transaction):
        computation = _execute_frontier_transaction(self, transaction)

        #
        # EIP161 state clearing
        #
        touched_accounts = collect_touched_accounts(computation)

        with self.state_db() as state_db:
            for account in touched_accounts:
                if state_db.account_exists(account) and state_db.account_is_empty(account):
                    self.logger.debug(
                        "CLEARING EMPTY ACCOUNT: %s",
                        encode_hex(account),
                    )
                    state_db.delete_account(account)

        return computation
