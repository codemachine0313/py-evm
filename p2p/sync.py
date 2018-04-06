import logging

from evm.db.chain import AsyncChainDB
from p2p.cancel_token import CancelToken
from p2p.exceptions import OperationCancelled
from p2p.peer import PeerPool
from p2p.chain import ChainSyncer
from p2p.state import StateDownloader


class FullNodeSyncer:
    logger = logging.getLogger("p2p.sync.FullNodeSyncer")

    def __init__(self, chaindb: AsyncChainDB, peer_pool: PeerPool) -> None:
        self.chaindb = chaindb
        self.peer_pool = peer_pool
        self.cancel_token = CancelToken('FullNodeSyncer')

    async def run(self) -> None:
        # Fast-sync chain data.
        chain_syncer = ChainSyncer(self.chaindb, self.peer_pool, self.cancel_token)
        try:
            await chain_syncer.run()
        finally:
            await chain_syncer.stop()

        # Download state for our current head.
        head = self.chaindb.get_canonical_head()
        downloader = StateDownloader(
            self.chaindb.db, head.state_root, self.peer_pool, self.cancel_token)
        try:
            await downloader.run()
        finally:
            await downloader.stop()

        # TODO: Run the regular sync.

    async def stop(self):
        self.cancel_token.trigger()


def _test():
    import argparse
    import asyncio
    from concurrent.futures import ProcessPoolExecutor
    import signal
    from p2p import ecies
    from p2p.peer import ETHPeer, HardCodedNodesPeerPool
    from evm.chains.ropsten import RopstenChain
    from evm.db.backends.level import LevelDB
    from tests.p2p.integration_test_helpers import FakeAsyncChainDB
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

    parser = argparse.ArgumentParser()
    parser.add_argument('-db', type=str, required=True)
    args = parser.parse_args()

    chaindb = FakeAsyncChainDB(LevelDB(args.db))
    peer_pool = HardCodedNodesPeerPool(
        ETHPeer, chaindb, RopstenChain.network_id, ecies.generate_privkey(), min_peers=5)
    asyncio.ensure_future(peer_pool.run())

    loop = asyncio.get_event_loop()
    loop.set_default_executor(ProcessPoolExecutor())

    syncer = FullNodeSyncer(chaindb, peer_pool)

    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(sig, syncer.cancel_token.trigger)

    async def run():
        try:
            await syncer.run()
        except OperationCancelled:
            pass
        await peer_pool.stop()

    loop.run_until_complete(run())
    loop.close()


if __name__ == "__main__":
    _test()
