#!/usr/bin/env python3
# Copyright (c) 2015-2019 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test the ZMQ publisher mempoolremoved to notify us on a transaction that
was included in a block and thus removed from the mempool"""

from random import randint
from time import sleep, time

import zmq

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util_patched_zmq import ZMQSubscriber, removalReason


class ZMQTest (BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 1

    def skip_test_if_missing_module(self):
        self.skip_if_no_py3_zmq()
        self.skip_if_no_bitcoind_zmq()
        self.skip_if_no_wallet()

    def run_test(self):
        import zmq
        self.ctx = zmq.Context()
        try:
            self.test_mempool_removed()
        finally:
            # Destroy the ZMQ context.
            self.log.debug("Destroying ZMQ context")
            self.ctx.destroy(linger=None)

    def test_mempool_removed(self):
        address = 'tcp://127.0.0.1:{}'.format(randint(20000, 22222))
        socket = self.ctx.socket(zmq.SUB)
        socket.set(zmq.RCVTIMEO, 60000)
        topic = b'mempoolremoved'

        arg_zmq_mempoolremoved = "-zmqpub%s=%s" % (
            topic.decode(), address)

        node0 = self.nodes[0]

        subscriber = ZMQSubscriber(socket, topic)
        self.restart_node(0, [arg_zmq_mempoolremoved])
        sleep(0.2)
        socket.connect(address)

        self.log.info("Testing mempoolremoved BLOCK")
        txid = node0.sendtoaddress( node0.getnewaddress(), 1.0)
        node0.generatetoaddress(1, node0.getnewaddress())

        expected = {txid: 'BLOCK'}
        subscriber.check_mempoolremoved_messages(expected)

if __name__ == '__main__':
    ZMQTest().main()
