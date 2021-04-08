#!/usr/bin/env python3
"""Test the ZMQ publisher mempooladded to notify us on a transaction (and its
fee) that was added to the mempool"""

import zmq
import struct
from time import sleep
from random import randint

from test_framework.test_framework import BitcoinTestFramework
from test_framework.messages import CTransaction, COIN
from test_framework.util import assert_equal
from io import BytesIO
from test_framework.util_patched_zmq import ZMQSubscriber


class ZMQTest (BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 1

    def skip_test_if_missing_module(self):
        self.skip_if_no_py3_zmq()
        self.skip_if_no_bitcoind_zmq()
        self.skip_if_no_wallet()

    def run_test(self):
        self.ctx = zmq.Context()
        try:
            self.test_mempool_added()
        finally:
            # Destroy the ZMQ context.
            self.log.debug("Destroying ZMQ context")
            self.ctx.destroy(linger=None)

    def test_mempool_added(self):
        address = 'tcp://127.0.0.1:{}'.format(randint(20000, 50000))
        socket = self.ctx.socket(zmq.SUB)
        socket.set(zmq.RCVTIMEO, 60000)

        # Subscribe to the 'mempooladded' topic
        self.log.info("Testing ZMQ publisher mempooladded")
        subscriber = ZMQSubscriber(socket, b"mempooladded")

        self.restart_node(0, ["-zmqpub{}={}".format(subscriber.topic.decode(), address)])
        socket.connect(address)
        # Relax so that the subscriber is ready before publishing zmq messages
        sleep(0.2)

        node = self.nodes[0]
        txid = node.sendtoaddress(node.getnewaddress(), 1.0)
        self.sync_all()

        # Should receive a payload with three elements (txid rawtx, fee)
        payload = subscriber.receive_multi_payload()
        assert_equal(3, len(payload))

        # First payload element should be the txid
        r_txid = payload[0]
        assert_equal(txid, r_txid.hex())

        # Second payload element should be the raw transaction
        r_rawtx = payload[1]
        tx = CTransaction()
        tx.deserialize(BytesIO(r_rawtx))
        tx.calc_sha256()
        assert_equal(txid, tx.hash)

        # Third payload element should be the transaction fee
        r_fee = struct.unpack('<q', payload[2])[-1]
        assert_equal(int(node.getmempoolentry(txid)["fee"] * COIN), r_fee)

        self.log.info("Test the getzmqnotifications RPC for mempooladded")
        assert_equal(node.getzmqnotifications(), [{"type": "pubmempooladded", "address": address, "hwm": 100000}])


if __name__ == '__main__':
    ZMQTest().main()
