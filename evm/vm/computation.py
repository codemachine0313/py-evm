from abc import (
    ABCMeta,
    abstractmethod
)
from contextlib import contextmanager
import itertools
import logging
from typing import (  # noqa: F401
    Any,
    Callable,
    cast,
    Dict,
    Iterator,
    List,
    Tuple,
)

from eth_typing import (
    Address
)

from evm.db.state import (
    BaseAccountStateDB
)
from evm.constants import (
    GAS_MEMORY,
    GAS_MEMORY_QUADRATIC_DENOMINATOR,
)
from evm.exceptions import (
    Halt,
    VMError,
)
from evm.utils.datatypes import (
    Configurable,
)
from evm.utils.hexadecimal import (
    encode_hex,
)
from evm.utils.numeric import (
    ceil32,
)
from evm.utils.logging import (
    TraceLogger
)
from evm.validation import (
    validate_canonical_address,
    validate_is_bytes,
    validate_uint256,
)
from evm.vm.code_stream import (
    CodeStream,
)
from evm.vm.gas_meter import (
    GasMeter,
)
from evm.vm.logic.invalid import (
    InvalidOpcode,
)
from evm.vm.memory import (
    Memory,
)
from evm.vm.message import (
    Message,
)
from evm.vm.opcode import (  # noqa: F401
    Opcode
)
from evm.vm.stack import (
    Stack,
)
from evm.vm.state import (
    BaseState,
)
from evm.vm.transaction_context import (
    BaseTransactionContext
)


def memory_gas_cost(size_in_bytes: int) -> int:
    size_in_words = ceil32(size_in_bytes) // 32
    linear_cost = size_in_words * GAS_MEMORY
    quadratic_cost = size_in_words ** 2 // GAS_MEMORY_QUADRATIC_DENOMINATOR

    total_cost = linear_cost + quadratic_cost
    return total_cost


class BaseComputation(Configurable, metaclass=ABCMeta):
    """
    The execution computation
    """
    state = None
    msg = None
    transaction_context = None

    _memory = None
    _stack = None
    _gas_meter = None

    code = None

    children = None  # type: List[BaseComputation]

    _output = b''
    return_data = b''
    _error = None  # type: VMError

    _log_entries = None  # type: List[Tuple[int, bytes, List[int], bytes]]
    accounts_to_delete = None  # type: Dict[bytes, bytes]

    # VM configuration
    opcodes = None  # type: Dict[int, Opcode]
    _precompiles = None  # type: Dict[bytes, Callable[['BaseComputation'], Any]]

    logger = cast(TraceLogger, logging.getLogger('evm.vm.computation.Computation'))

    def __init__(self,
                 state: BaseState,
                 message: Message,
                 transaction_context: BaseTransactionContext) -> None:

        self.state = state
        self.msg = message
        self.transaction_context = transaction_context

        self._memory = Memory()
        self._stack = Stack()
        self._gas_meter = GasMeter(message.gas)

        self.children = []
        self.accounts_to_delete = {}
        self._log_entries = []

        code = message.code
        self.code = CodeStream(code)

    #
    # Convenience
    #
    @property
    def is_origin_computation(self) -> bool:
        """
        Is this computation the computation initiated by a transaction.
        """
        return self.msg.sender == self.transaction_context.origin

    @property
    def is_success(self) -> bool:
        return self._error is None

    @property
    def is_error(self) -> bool:
        return not self.is_success

    @property
    def should_burn_gas(self) -> bool:
        return self.is_error and self._error.burns_gas

    @property
    def should_return_gas(self) -> bool:
        return not self.should_burn_gas

    @property
    def should_erase_return_data(self) -> bool:
        return self.is_error and self._error.erases_return_data

    #
    # Execution
    #
    def prepare_child_message(self,
                              gas: int,
                              to: bytes,
                              value: int,
                              data: bytes,
                              code: bytes,
                              **kwargs: Any) -> Message:
        kwargs.setdefault('sender', self.msg.storage_address)

        child_message = Message(
            gas=gas,
            to=to,
            value=value,
            data=data,
            code=code,
            depth=self.msg.depth + 1,
            **kwargs
        )
        return child_message

    #
    # Memory Management
    #
    def extend_memory(self, start_position: int, size: int) -> None:
        validate_uint256(start_position, title="Memory start position")
        validate_uint256(size, title="Memory size")

        before_size = ceil32(len(self._memory))
        after_size = ceil32(start_position + size)

        before_cost = memory_gas_cost(before_size)
        after_cost = memory_gas_cost(after_size)

        self.logger.debug(
            "MEMORY: size (%s -> %s) | cost (%s -> %s)",
            before_size,
            after_size,
            before_cost,
            after_cost,
        )

        if size:
            if before_cost < after_cost:
                gas_fee = after_cost - before_cost
                self._gas_meter.consume_gas(
                    gas_fee,
                    reason=" ".join((
                        "Expanding memory",
                        str(before_size),
                        "->",
                        str(after_size),
                    ))
                )

            self._memory.extend(start_position, size)

    def memory_write(self, start_position: int, size: int, value: bytes) -> None:
        return self._memory.write(start_position, size, value)

    def memory_read(self, start_position: int, size: int) -> bytes:
        return self._memory.read(start_position, size)

    def consume_gas(self, amount: int, reason: str) -> None:
        return self._gas_meter.consume_gas(amount, reason)

    def return_gas(self, amount: int) -> None:
        return self._gas_meter.return_gas(amount)

    def refund_gas(self, amount: int) -> None:
        return self._gas_meter.refund_gas(amount)

    def stack_pop(self, num_items=1, type_hint=None):
        return self._stack.pop(num_items, type_hint)

    def stack_push(self, value):
        return self._stack.push(value)

    def stack_swap(self, position):
        return self._stack.swap(position)

    def stack_dup(self, position):
        return self._stack.dup(position)

    #
    # Computed properties.
    #
    @property
    def output(self) -> bytes:
        if self.should_erase_return_data:
            return b''
        else:
            return self._output

    @output.setter
    def output(self, value: bytes) -> None:
        validate_is_bytes(value)
        self._output = value

    #
    # Runtime operations
    #
    def apply_child_computation(self, child_msg: Message) -> 'BaseComputation':
        child_computation = self.generate_child_computation(child_msg)
        self.add_child_computation(child_computation)
        return child_computation

    def generate_child_computation(self, child_msg: Message) -> 'BaseComputation':
        if child_msg.is_create:
            child_computation = self.__class__(
                self.state,
                child_msg,
                self.transaction_context,
            ).apply_create_message()
        else:
            child_computation = self.__class__(
                self.state,
                child_msg,
                self.transaction_context,
            ).apply_message()
        return child_computation

    def add_child_computation(self, child_computation: 'BaseComputation') -> None:
        if child_computation.is_error:
            if child_computation.msg.is_create:
                self.return_data = child_computation.output
            elif child_computation.should_burn_gas:
                self.return_data = b''
            else:
                self.return_data = child_computation.output
        else:
            if child_computation.msg.is_create:
                self.return_data = b''
            else:
                self.return_data = child_computation.output
        self.children.append(child_computation)

    def register_account_for_deletion(self, beneficiary: Address) -> None:
        validate_canonical_address(beneficiary, title="Self destruct beneficiary address")

        if self.msg.storage_address in self.accounts_to_delete:
            raise ValueError(
                "Invariant.  Should be impossible for an account to be "
                "registered for deletion multiple times"
            )
        self.accounts_to_delete[self.msg.storage_address] = beneficiary

    def add_log_entry(self, account: Address, topics: List[int], data: bytes) -> None:
        validate_canonical_address(account, title="Log entry address")
        for topic in topics:
            validate_uint256(topic, title="Log entry topic")
        validate_is_bytes(data, title="Log entry data")
        self._log_entries.append(
            (self.transaction_context.get_next_log_counter(), account, topics, data))

    #
    # Getters
    #
    def get_accounts_for_deletion(self) -> Tuple[Tuple[bytes, bytes], ...]:
        if self.is_error:
            return tuple()
        else:
            return tuple(dict(itertools.chain(
                self.accounts_to_delete.items(),
                *(child.get_accounts_for_deletion() for child in self.children)
            )).items())

    def _get_log_entries(self) -> List[Tuple[int, bytes, List[int], bytes]]:
        """Return the log entries for this computation and its children.

        They are sorted in the same order they were emitted during the transaction processing, and
        include the sequential counter as the first element of the tuple representing every entry.
        """
        if self.is_error:
            return []
        else:
            return sorted(itertools.chain(
                self._log_entries,
                *(child._get_log_entries() for child in self.children)
            ))

    def get_log_entries(self) -> Tuple[Tuple[bytes, List[int], bytes], ...]:
        return tuple(log[1:] for log in self._get_log_entries())

    def get_gas_refund(self) -> int:
        if self.is_error:
            return 0
        else:
            return self._gas_meter.gas_refunded + sum(c.get_gas_refund() for c in self.children)

    def get_gas_used(self) -> int:
        if self.should_burn_gas:
            return self.msg.gas
        else:
            return max(
                0,
                self.msg.gas - self._gas_meter.gas_remaining,
            )

    def get_gas_remaining(self) -> int:
        if self.should_burn_gas:
            return 0
        else:
            return self._gas_meter.gas_remaining

    @contextmanager
    def state_db(self, read_only: bool = False) -> Iterator[BaseAccountStateDB]:
        with self.state.state_db(read_only) as state_db:
            yield state_db

    #
    # Context Manager API
    #
    def __enter__(self) -> 'BaseComputation':
        self.logger.debug(
            (
                "COMPUTATION STARTING: gas: %s | from: %s | to: %s | value: %s "
                "| depth %s | static: %s"
            ),
            self.msg.gas,
            encode_hex(self.msg.sender),
            encode_hex(self.msg.to),
            self.msg.value,
            self.msg.depth,
            "y" if self.msg.is_static else "n",
        )

        return self

    def __exit__(self, exc_type: None, exc_value: None, traceback: None) -> None:
        if exc_value and isinstance(exc_value, VMError):
            self.logger.debug(
                (
                    "COMPUTATION ERROR: gas: %s | from: %s | to: %s | value: %s | "
                    "depth: %s | static: %s | error: %s"
                ),
                self.msg.gas,
                encode_hex(self.msg.sender),
                encode_hex(self.msg.to),
                self.msg.value,
                self.msg.depth,
                "y" if self.msg.is_static else "n",
                exc_value,
            )
            self._error = exc_value
            if self.should_burn_gas:
                self.consume_gas(
                    self._gas_meter.gas_remaining,
                    reason=" ".join((
                        "Zeroing gas due to VM Exception:",
                        str(exc_value),
                    )),
                )

            # suppress VM exceptions
            return True
        elif exc_type is None:
            self.logger.debug(
                (
                    "COMPUTATION SUCCESS: from: %s | to: %s | value: %s | "
                    "depth: %s | static: %s | gas-used: %s | gas-remaining: %s"
                ),
                encode_hex(self.msg.sender),
                encode_hex(self.msg.to),
                self.msg.value,
                self.msg.depth,
                "y" if self.msg.is_static else "n",
                self.msg.gas - self._gas_meter.gas_remaining,
                self._gas_meter.gas_remaining,
            )

    #
    # State Transition
    #
    @abstractmethod
    def apply_message(self) -> 'BaseComputation':
        """
        Execution of an VM message.
        """
        raise NotImplementedError("Must be implemented by subclasses")

    @abstractmethod
    def apply_create_message(self) -> 'BaseComputation':
        """
        Execution of an VM message to create a new contract.
        """
        raise NotImplementedError("Must be implemented by subclasses")

    @classmethod
    def apply_computation(cls,
                          state: BaseState,
                          message: Message,
                          transaction_context: BaseTransactionContext) -> 'BaseComputation':
        """
        Perform the computation that would be triggered by the VM message.
        """
        with cls(state, message, transaction_context) as computation:
            # Early exit on pre-compiles
            if message.code_address in computation.precompiles:
                computation.precompiles[message.code_address](computation)
                return computation

            for opcode in computation.code:
                opcode_fn = computation.get_opcode_fn(opcode)

                computation.logger.trace(
                    "OPCODE: 0x%x (%s) | pc: %s",
                    opcode,
                    opcode_fn.mnemonic,
                    max(0, computation.code.pc - 1),
                )

                try:
                    opcode_fn(computation=computation)
                except Halt:
                    break
        return computation

    #
    # Opcode API
    #
    @property
    def precompiles(self) -> Dict[bytes, Callable[['BaseComputation'], Any]]:
        if self._precompiles is None:
            return dict()
        else:
            return self._precompiles

    def get_opcode_fn(self, opcode):
        try:
            return self.opcodes[opcode]
        except KeyError:
            return InvalidOpcode(opcode)
