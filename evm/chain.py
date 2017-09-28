from __future__ import absolute_import

from cytoolz import (
    assoc,
)

from eth_utils import (
    to_tuple,
)
from evm.consensus.pow import (
    check_pow,
)
from evm.constants import (
    GENESIS_BLOCK_NUMBER,
    MAX_UNCLE_DEPTH,
)
from evm.exceptions import (
    BlockNotFound,
    ValidationError,
    VMNotFound,
)
from evm.validation import (
    validate_block_number,
    validate_uint256,
    validate_word,
)

from evm.rlp.headers import (
    BlockHeader,
)

from evm.utils.blocks import (
    add_block_number_to_hash_lookup,
    get_score,
    get_block_header_by_hash,
    lookup_block_hash,
)
from evm.utils.blocks import (
    persist_block_to_db,
)
from evm.utils.chain import (
    generate_vms_by_range,
)
from evm.utils.hexadecimal import (
    encode_hex,
)
from evm.utils.rlp import (
    ensure_imported_block_unchanged,
)

from evm.db.state import State


class Chain(object):
    """
    An Chain is a combination of one or more VM classes.  Each VM is associated
    with a range of blocks.  The Chain class acts as a wrapper around these other
    VM classes, delegating operations to the appropriate VM depending on the
    current block number.
    """
    db = None
    header = None

    vms_by_range = None

    def __init__(self, db, header):
        if not self.vms_by_range:
            raise ValueError(
                "The Chain class cannot be instantiated with an empty `vms_by_range`"
            )

        self.db = db
        self.header = header

    @classmethod
    def configure(cls, name, vm_configuration, **overrides):
        if 'vms_by_range' in overrides:
            raise ValueError("Cannot override vms_by_range.")

        for key in overrides:
            if not hasattr(cls, key):
                raise TypeError(
                    "The Chain.configure cannot set attributes that are not "
                    "already present on the base class.  The attribute `{0}` was "
                    "not found on the base class `{1}`".format(key, cls)
                )

        # Organize the Chain classes by their starting blocks.
        overrides['vms_by_range'] = generate_vms_by_range(vm_configuration)

        return type(name, (cls,), overrides)

    #
    # Convenience and Helpers
    #
    def get_block(self):
        """
        Passthrough helper to the current VM class.
        """
        return self.get_vm().block

    def create_transaction(self, *args, **kwargs):
        """
        Passthrough helper to the current VM class.
        """
        return self.get_vm().create_transaction(*args, **kwargs)

    def create_unsigned_transaction(self, *args, **kwargs):
        """
        Passthrough helper to the current VM class.
        """
        return self.get_vm().create_unsigned_transaction(*args, **kwargs)

    def create_header_from_parent(self, parent_header, **header_params):
        """
        Passthrough helper to the VM class of the block descending from the
        given header.
        """
        return self.get_vm_class_for_block_number(
            block_number=parent_header.block_number + 1,
        ).create_header_from_parent(parent_header, **header_params)

    #
    # Chain Operations
    #
    def get_vm_class_for_block_number(self, block_number):
        """
        Return the vm class for the given block number.
        """
        validate_block_number(block_number)
        for n in reversed(self.vms_by_range.keys()):
            if block_number >= n:
                return self.vms_by_range[n]
        else:
            raise VMNotFound("No vm available for block #{0}".format(block_number))

    def get_vm(self, header=None):
        """
        Return the vm instance for the given block number.
        """
        if header is None:
            header = self.header

        vm_class = self.get_vm_class_for_block_number(header.block_number)
        return vm_class(header=header, db=self.db)

    #
    # Block Retrieval
    #
    def get_block_header_by_hash(self, block_hash):
        return get_block_header_by_hash(self.db, block_hash)

    def get_canonical_block_by_number(self, block_number):
        """
        Returns the block with the given number in the canonical chain.

        Raises BlockNotFound if there's no block with the given number in the
        canonical chain.
        """
        validate_uint256(block_number, title="Block Number")
        return self.get_block_by_hash(lookup_block_hash(self.db, block_number))

    def get_block_by_hash(self, block_hash):
        """
        Returns the requested block as specified by block hash.
        """
        validate_word(block_hash, title="Block Hash")
        block_header = self.get_block_header_by_hash(block_hash)
        vm = self.get_vm(block_header)
        return vm.get_block_by_header(block_header)

    #
    # Chain Initialization
    #
    @classmethod
    def from_genesis(cls,
                     db,
                     genesis_params,
                     genesis_state=None):
        """
        Initialize the Chain from a genesis state.
        """
        state_db = State(db)

        if genesis_state is None:
            genesis_state = {}

        for account, account_data in genesis_state.items():
            state_db.set_balance(account, account_data['balance'])
            state_db.set_nonce(account, account_data['nonce'])
            state_db.set_code(account, account_data['code'])

            for slot, value in account_data['storage'].items():
                state_db.set_storage(account, slot, value)

        if 'state_root' not in genesis_params:
            # If the genesis state_root was not specified, use the value
            # computed from the initialized state database.
            genesis_params = assoc(genesis_params, 'state_root', state_db.root_hash)
        elif genesis_params['state_root'] != state_db.root_hash:
            # If the genesis state_root was specified, validate that it matches
            # the computed state from the initialized state database.
            raise ValidationError(
                "The provided genesis state root does not match the computed "
                "genesis state root.  Got {0}.  Expected {1}".format(
                    state_db.root_hash,
                    genesis_params['state_root'],
                )
            )

        genesis_header = BlockHeader(**genesis_params)
        genesis_chain = cls(db, genesis_header)
        persist_block_to_db(db, genesis_chain.get_block())
        add_block_number_to_hash_lookup(db, genesis_chain.get_block())

        return cls(db, genesis_chain.create_header_from_parent(genesis_header))

    #
    # Mining and Execution API
    #
    def apply_transaction(self, transaction):
        """
        Apply the transaction to the current head block of the Chain.
        """
        vm = self.get_vm()
        return vm.apply_transaction(transaction)

    def import_block(self, block, perform_validation=True):
        """
        Import a complete block.
        """
        if block.number > self.header.block_number:
            raise ValidationError(
                "Attempt to import block #{0}.  Cannot import block with number "
                "greater than current block #{1}.".format(
                    block.number,
                    self.header.block_number,
                )
            )

        parent_chain = self.get_chain_at_block_parent(block)
        imported_block = parent_chain.get_vm().import_block(block)

        # Validate the imported block.
        if perform_validation:
            ensure_imported_block_unchanged(imported_block, block)
            self.validate_block(imported_block)

        persist_block_to_db(self.db, imported_block)
        if self.should_be_canonical_chain_head(imported_block):
            self.set_as_canonical_chain_head(imported_block)

        return imported_block

    def mine_block(self, *args, **kwargs):
        """
        Mines the current block.
        """
        mined_block = self.get_vm().mine_block(*args, **kwargs)

        self.validate_block(mined_block)

        persist_block_to_db(self.db, mined_block)
        if self.should_be_canonical_chain_head(mined_block):
            self.set_as_canonical_chain_head(mined_block)

        return mined_block

    def get_chain_at_block_parent(self, block):
        """
        Returns a `Chain` instance with this block's parent at the chain head.
        """
        try:
            parent_header = self.get_block_header_by_hash(block.header.parent_hash)
        except BlockNotFound:
            raise ValidationError("Parent ({0}) of block {1} not found".format(
                block.header.parent_hash,
                block.header.hash
            ))

        init_header = self.create_header_from_parent(parent_header)
        return type(self)(self.db, init_header)

    def should_be_canonical_chain_head(self, block):
        """
        TODO: fill this in.
        """
        current_head = self.get_block_by_hash(self.header.parent_hash)
        return get_score(self.db, block.hash) > get_score(self.db, current_head.hash)

    def set_as_canonical_chain_head(self, block):
        """
        Sets the block as the canonical chain HEAD.
        """
        for b in reversed(self.find_common_ancestor(block)):
            add_block_number_to_hash_lookup(self.db, b)
        self.header = self.create_header_from_parent(block.header)

    @to_tuple
    def find_common_ancestor(self, block):
        """
        TODO: fill this in.
        """
        b = block
        while b.number >= GENESIS_BLOCK_NUMBER:
            yield b
            try:
                orig = self.get_canonical_block_by_number(b.number)
                if orig.hash == b.hash:
                    # Found the common ancestor, stop.
                    break
            except KeyError:
                # This just means the block is not on the canonical chain.
                pass
            b = self.get_block_by_hash(b.header.parent_hash)

    @to_tuple
    def get_ancestors(self, limit):
        lower_limit = max(self.header.block_number - limit, 0)
        for n in reversed(range(lower_limit, self.header.block_number)):
            yield self.get_canonical_block_by_number(n)

    #
    # Validation API
    #
    def validate_block(self, block):
        """
        Performs validation on a block that is either being mined or imported.

        Since block validation (specifically the uncle validation must have
        access to the ancestor blocks, this validation must occur at the Chain
        level.

        TODO: move the `seal` validation down into the vm.
        """
        self.validate_seal(block.header)
        self.validate_uncles(block)

    def validate_uncles(self, block):
        recent_ancestors = dict(
            (ancestor.hash, ancestor)
            for ancestor in self.get_ancestors(MAX_UNCLE_DEPTH + 1),
        )
        recent_uncles = []
        for ancestor in recent_ancestors.values():
            recent_uncles.extend([uncle.hash for uncle in ancestor.uncles])
        recent_ancestors[block.hash] = block
        recent_uncles.append(block.hash)

        for uncle in block.uncles:
            if uncle.hash in recent_ancestors:
                raise ValidationError(
                    "Duplicate uncle: {0}".format(encode_hex(uncle.hash)))
            recent_uncles.append(uncle.hash)

            if uncle.hash in recent_ancestors:
                raise ValidationError(
                    "Uncle {0} cannot be an ancestor of {1}".format(
                        encode_hex(uncle.hash), encode_hex(block.hash)))

            if uncle.parent_hash not in recent_ancestors or (
               uncle.parent_hash == block.header.parent_hash):
                raise ValidationError(
                    "Uncle's parent {0} is not an ancestor of {1}".format(
                        encode_hex(uncle.parent_hash), encode_hex(block.hash)))

            self.validate_seal(uncle)

    def validate_seal(self, header):
        check_pow(
            header.block_number, header.mining_hash,
            header.mix_hash, header.nonce, header.difficulty)
