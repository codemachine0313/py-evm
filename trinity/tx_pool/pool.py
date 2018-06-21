import logging
from typing import (
    cast,
    Iterable,
    List
)
import uuid

from bloom_filter import (
    BloomFilter
)

from p2p.eth import (
    Transactions
)
from p2p.peer import (
    BasePeer,
    ETHPeer,
    PeerPool,
    PeerPoolSubscriber,
)
from p2p.rlp import (
    P2PTransaction
)
from p2p.service import (
    BaseService
)


class TxPool(BaseService, PeerPoolSubscriber):
    """
    The :class:`~trinity.tx_pool.pool.TxPool` class is responsible for holding and relaying
    of transactions, represented as :class:`~evm.rlp.transactions.BaseTransaction` among the
    connected peers.

      .. note::

        This is a minimal viable implementation that only relays transactions but doesn't actually
        hold on to them yet. It's still missing many features of a grown up transaction pool.
    """
    logger = logging.getLogger("trinity.tx_pool.TxPool")

    def __init__(self, peer_pool: PeerPool) -> None:
        super().__init__()
        self._peer_pool = peer_pool
        # 1m should give us 9000 blocks before that filter becomes less reliable
        # It should take up about 1mb of memory
        self._bloom = BloomFilter(max_elements=1000000)
        self._bloom_salt = str(uuid.uuid4())

    def register_peer(self, peer: BasePeer) -> None:
        pass

    async def _run(self) -> None:
        self.logger.info("Running Tx Pool")

        with self.subscribe(self._peer_pool):
            while True:
                peer: ETHPeer
                peer, cmd, msg = await self.wait(
                    self.msg_queue.get(), token=self.cancel_token)

                if isinstance(cmd, Transactions):
                    await self._handle_tx(peer, msg)

    async def _handle_tx(self, peer: ETHPeer, txs: List[P2PTransaction]) -> None:

        self.logger.debug('Received transactions from %r: %r', peer, txs)

        self._add_txs_to_bloom(peer, txs)

        for receiving_peer in self._peer_pool.peers:
            receiving_peer = cast(ETHPeer, receiving_peer)

            if receiving_peer is peer:
                continue

            filtered_tx = self._filter_tx_for_peer(receiving_peer, txs)
            if len(filtered_tx) == 0:
                continue

            self.logger.debug(
                'Sending transactions to %r: %r',
                receiving_peer,
                filtered_tx
            )
            receiving_peer.sub_proto.send_transactions(filtered_tx)
            self._add_txs_to_bloom(receiving_peer, filtered_tx)

    def _filter_tx_for_peer(
            self,
            peer: BasePeer,
            txs: List[P2PTransaction]) -> List[P2PTransaction]:

        return [
            val for val in txs
            if self._construct_bloom_entry(peer, val) not in self._bloom
        ]

    def _construct_bloom_entry(self, peer: BasePeer, tx: P2PTransaction) -> bytes:
        return "{!r}-{}-{}".format(peer.remote, tx.hash, self._bloom_salt).encode()

    def _add_txs_to_bloom(self, peer: BasePeer, txs: Iterable[P2PTransaction]) -> None:
        for val in txs:
            self._bloom.add(self._construct_bloom_entry(peer, val))

    async def _cleanup(self) -> None:
        self.logger.info("Stopping Tx Pool...")
