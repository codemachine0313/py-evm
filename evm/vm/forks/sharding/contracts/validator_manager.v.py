# Information about validators
validators: public({
    # Amount of wei the validator holds
    deposit: wei_value,
    # Address of the validator
    addr: address,
}[num])

# Number of validators
num_validators: public(num)

# Collation headers
collation_headers: public({
    parent_collation_hash: bytes32,
    score: num,
}[bytes32][num])

# Receipt data
receipts: public({
    shard_id: num,
    tx_startgas: num,
    tx_gasprice: num,
    value: wei_value,
    sender: address,
    to: address,
    data: bytes <= 4096,
}[num])

# Current head of each shard
shard_head: public(bytes32[num])

# Number of receipts
num_receipts: num

# Indexs of empty slots caused by the function `withdraw`
empty_slots_stack: num[num]

# The top index of the stack in empty_slots_stack
empty_slots_stack_top: num

# Gas limit of the signature validation code
sig_gas_limit: num

# Has the validator deposited before?
is_validator_deposited: public(bool[address])

# Log the latest period number of the shard
period_head: public(num[num])


# Configuration Parameter

# The exact deposit size which you have to deposit to become a validator
deposit_size: wei_value

# Number of blocks in one period
period_length: num

# Number of shards
shard_count: num

# Number of periods ahead of current period, which the contract
# is able to return the collator of that period
lookahead_periods: num

# Events
# TODO: should be added after the issue "In log declaration, `bytes` must be smaller 32" is solved.
# CollationAdded(indexed uint256 shard, bytes collationHeader, bool isNewHead, uint256 score)

@public
def __init__():
    self.num_validators = 0
    self.empty_slots_stack_top = 0
    # 10 ** 20 wei = 100 ETH
    self.deposit_size = 100000000000000000000
    self.sig_gas_limit = 40000
    self.period_length = 5
    self.shard_count = 100
    self.lookahead_periods = 4


# Checks if empty_slots_stack_top is empty
@internal
def is_stack_empty() -> bool:
    return (self.empty_slots_stack_top == 0)


# Pushes one num to empty_slots_stack
@internal
def stack_push(index: num):
    self.empty_slots_stack[self.empty_slots_stack_top] = index
    self.empty_slots_stack_top += 1


# Pops one num out of empty_slots_stack
@internal
def stack_pop() -> num:
    if self.is_stack_empty():
        return -1
    self.empty_slots_stack_top -= 1
    return self.empty_slots_stack[self.empty_slots_stack_top]


# Returns the current maximum index for validators mapping
@internal
def get_validators_max_index() -> num:
    zero_addr = 0x0000000000000000000000000000000000000000
    activate_validator_num = 0
    all_validator_slots_num = self.num_validators + self.empty_slots_stack_top

    # TODO: any better way to iterate the mapping?
    for i in range(1024):
        if i >= all_validator_slots_num:
            break
        if self.validators[i].addr != zero_addr:
            activate_validator_num += 1
    return activate_validator_num + self.empty_slots_stack_top


# Adds a validator to the validator set, with the validator's size being the msg.value
# (ie. amount of ETH deposited) in the function call. Returns the validator index.
@public
@payable
def deposit() -> num:
    validator_addr = msg.sender
    assert not self.is_validator_deposited[validator_addr]
    assert msg.value == self.deposit_size
    # find the empty slot index in validators set
    if not self.is_stack_empty():
        index = self.stack_pop()
    else:
        index = self.num_validators
    self.validators[index] = {
        deposit: msg.value,
        addr: validator_addr,
    }
    self.num_validators += 1
    self.is_validator_deposited[validator_addr] = True

    # TODO: determine the signature of the log Deposit
    raw_log(
        [sha3("deposit()"), as_bytes32(validator_addr)],
        concat('', as_bytes32(index))
    )

    return index


# Verifies that the signature is correct (ie. a call with 200000 gas, validationCodeAddr as
# destination, 0 value and sha3("withdraw") + sig as data returns 1), and if it is removes
# the validator from the validator set and refunds the deposited ETH.
@public
@payable
def withdraw(validator_index: num, sig: bytes <= 4096) -> bool:
    msg_hash = sha3("withdraw")
    validator_addr = self.validators[validator_index].addr
    validator_deposit = self.validators[validator_index].deposit
    assert msg.sender == validator_addr
    self.is_validator_deposited[validator_addr] = False
    self.validators[validator_index] = {
        deposit: 0,
        addr: None,
    }
    self.stack_push(validator_index)
    self.num_validators -= 1

    send(validator_addr, validator_deposit)

    # TODO: determine the signature of the log Withdraw
    raw_log(
        [sha3("withdraw(int128,bytes4096)")],
        concat('', as_bytes32(validator_index)),
    )


# Uses a block hash as a seed to pseudorandomly select a signer from the validator set.
# [TODO] Chance of being selected should be proportional to the validator's deposit.
# Should be able to return a value for the current period or any future period up to.
@public
@constant
def get_eligible_proposer(shard_id: num, period: num) -> address:
    assert period >= self.lookahead_periods
    assert (period - self.lookahead_periods) * self.period_length < block.number
    assert self.num_validators > 0
    return self.validators[
        as_num128(
            num256_mod(
                as_num256(
                    sha3(
                        concat(
                            # TODO: should check further if this safe or not
                            blockhash((period - self.lookahead_periods) * self.period_length),
                            as_bytes32(shard_id)
                        )
                    )
                ),
                as_num256(self.get_validators_max_index())
            )
        )
    ].addr


# Attempts to process a collation header, returns True on success, reverts on failure.
@public
def add_header(
        shard_id: num,
        expected_period_number: num,
        period_start_prevhash: bytes32,
        parent_collation_hash: bytes32,
        tx_list_root: bytes32,
        collation_coinbase: address,
        post_state_root: bytes32,
        receipt_root: bytes32,
        collation_number: num,
    ) -> bool:
    zero_addr = 0x0000000000000000000000000000000000000000

    # Check if the header is valid
    assert (shard_id >= 0) and (shard_id < self.shard_count)
    assert block.number >= self.period_length
    assert expected_period_number == floor(decimal(block.number / self.period_length))
    assert period_start_prevhash == blockhash(expected_period_number * self.period_length - 1)

    # Check if this header already exists
    header_bytes = concat(
        as_bytes32(shard_id),
        as_bytes32(expected_period_number),
        period_start_prevhash,
        parent_collation_hash,
        tx_list_root,
        as_bytes32(collation_coinbase),
        post_state_root,
        receipt_root,
        as_bytes32(collation_number),
    )
    entire_header_hash = sha3(header_bytes)
    assert entire_header_hash != as_bytes32(0)
    assert self.collation_headers[shard_id][entire_header_hash].score == 0
    # Check whether the parent exists.
    # if (parent_collation_hash == 0), i.e., is the genesis,
    # then there is no need to check.
    if parent_collation_hash != as_bytes32(0):
        assert (parent_collation_hash == as_bytes32(0)) or (self.collation_headers[shard_id][parent_collation_hash].score > 0)
    # Check if only one collation in one period
    assert self.period_head[shard_id] < expected_period_number

    # Check the signature with validation_code_addr
    validator_addr = self.get_eligible_proposer(shard_id, block.number / self.period_length)
    if validator_addr == zero_addr:
        return False
    assert msg.sender == validator_addr

    # Check score == collation_number
    _score = self.collation_headers[shard_id][parent_collation_hash].score + 1
    assert collation_number == _score

    # Add the header
    self.collation_headers[shard_id][entire_header_hash] = {
        parent_collation_hash: parent_collation_hash,
        score: _score
    }

    # Update the latest period number
    self.period_head[shard_id] = expected_period_number

    # Determine the head
    is_new_head = False
    if _score > self.collation_headers[shard_id][self.shard_head[shard_id]].score:
        self.shard_head[shard_id] = entire_header_hash
        is_new_head = True

    # Emit a log which is equivalent to
    # CollationAdded: __log__({shard_id: indexed(num), collation_header: bytes <= 4096, is_new_head: bool, score: num})
    # TODO: should be replaced by `log.CollationAdded`
    if is_new_head:
        new_head_in_num = 1
    else:
        new_head_in_num = 0
    raw_log(
        [
            sha3("CollationAdded(int128,bytes4096,bool,int128)"),
            as_bytes32(shard_id),
        ],
        concat(
            header_bytes,
            as_bytes32(new_head_in_num),
            as_bytes32(_score),
        )
    )

    return True


# Returns the gas limit that collations can currently have (by default make
# this function always answer 10 million).
@public
@constant
def get_collation_gas_limit() -> num:
    return 10000000


# Records a request to deposit msg.value ETH to address to in shard shard_id
# during a future collation. Saves a `receipt ID` for this request,
# also saving `msg.sender`, `msg.value`, `to`, `shard_id`, `startgas`,
# `gasprice`, and `data`.
@public
@payable
def tx_to_shard(to: address, shard_id: num, tx_startgas: num, tx_gasprice: num, data: bytes <= 4096) -> num:
    self.receipts[self.num_receipts] = {
        shard_id: shard_id,
        tx_startgas: tx_startgas,
        tx_gasprice: tx_gasprice,
        value: msg.value,
        sender: msg.sender,
        to: to,
        data: data
    }
    receipt_id = self.num_receipts
    self.num_receipts += 1

    # TODO: determine the signature of the log TxToShard
    raw_log(
        [sha3("tx_to_shard(address,num,num,num,bytes4096)"), as_bytes32(to), as_bytes32(shard_id)],
        concat('', as_bytes32(receipt_id))
    )

    return receipt_id


# Updates the tx_gasprice in receipt receipt_id, and returns True on success.
@public
@payable
def update_gasprice(receipt_id: num, tx_gasprice: num) -> bool:
    assert self.receipts[receipt_id].sender == msg.sender
    self.receipts[receipt_id].tx_gasprice = tx_gasprice
    return True
