#!/usr/bin/env python3
# Copyright (c) 2015-2019 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test the ZMQ publisher mempoolremoved to notify us on a transaction that
expired from the mempool"""

from random import randint
from time import sleep, time

import zmq

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal, find_vout_for_address
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
        address = 'tcp://127.0.0.1:{}'.format(randint(20000, 50000))
        socket = self.ctx.socket(zmq.SUB)
        socket.set(zmq.RCVTIMEO, 60000)
        topic = b"mempoolremoved"

        arg_zmq_mempoolremoved = "-zmqpub%s=%s" % (
            topic.decode(), address)

        node = self.nodes[0]

        self.log.info("Testing ZMQ publisher mempoolremoved")
        subscriber = ZMQSubscriber(socket, topic)
        self.restart_node(0, [arg_zmq_mempoolremoved])
        # Relax so that the subscriber is ready before publishing zmq messages
        sleep(0.2)
        socket.connect(address)

        self.log.info(
            "Testing the getzmqnotifications RPC for mempoolremoved")
        assert_equal(node.getzmqnotifications(), [
                        {"type": "pubmempoolremoved", "address": address, "hwm": 100000}])

        self.log.info("Testing removal reason EXPIRY")
        DEFAULT_MEMPOOL_EXPIRY = 336

        # Send a parent transaction that will expire.
        parent_address = node.getnewaddress()
        parent_txid = node.sendtoaddress(parent_address, 1.0)

        # Set the mocktime to the arrival time of the parent transaction.
        entry_time = node.getmempoolentry(parent_txid)["time"]
        node.setmocktime(entry_time)

        # Create child transaction spending the parent transaction
        vout = find_vout_for_address(node, parent_txid, parent_address)
        inputs = [{'txid': parent_txid, 'vout': vout}]
        outputs = {node.getnewaddress(): 0.99}
        child_raw = node.createrawtransaction(inputs, outputs)
        child_signed = node.signrawtransactionwithwallet(child_raw)["hex"]

        # Let half of the timeout elapse and broadcast the child transaction.
        half_expiry_time = entry_time + \
            int(60 * 60 * DEFAULT_MEMPOOL_EXPIRY/2)
        node.setmocktime(half_expiry_time)
        child_txid = node.sendrawtransaction(child_signed)

        # Let most of the timeout elapse and check that the parent tx is still
        # in the mempool.
        nearly_expiry_time = entry_time + 60 * 60 * DEFAULT_MEMPOOL_EXPIRY - 5
        node.setmocktime(nearly_expiry_time)
        # Expiry of mempool transactions is only checked when a new transaction
        # is added to the to the mempool.
        node.sendtoaddress(node.getnewaddress(), 1.0)
        assert_equal(entry_time, node.getmempoolentry(parent_txid)["time"])

        # Transaction should be evicted from the mempool after the expiry time
        # has passed.
        expiry_time = entry_time + 60 * 60 * DEFAULT_MEMPOOL_EXPIRY + 5
        node.setmocktime(expiry_time)
        # Expiry of mempool transactions is only checked when a new transaction
        # is added to the to the mempool.
        node.sendtoaddress(node.getnewaddress(), 1.0)

        # The ZMQ interface should receive two removed transactions (the
        # parent and the child), however we don't know the removal order
        expected = {parent_txid: 'EXPIRY', child_txid: 'EXPIRY'}
        subscriber.check_mempoolremoved_messages(expected)

if __name__ == '__main__':
    ZMQTest().main()
