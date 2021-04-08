#!/usr/bin/env python3
# Copyright (c) 2015-2019 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test the ZMQ publisher mempoolremoved to notify us on a transaction that
was removed from the the mempool in a reorg"""


from random import randint
from time import sleep

import zmq

from test_framework.address import ADDRESS_BCRT1_UNSPENDABLE
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
        arg_txindex = "-txindex=1"

        node = self.nodes[0]

        self.log.info("Testing ZMQ publisher mempoolremoved")
        subscriber = ZMQSubscriber(socket, topic)
        self.restart_node(0,[arg_txindex, arg_zmq_mempoolremoved])
        sleep(0.2)
        socket.connect(address)

        # Test that transactions removed from our mempool due to a reorg are notified
        # There are several other reasons a tx could be removed for REORG:
        # - a spend from a coinbase output that is no longer mature (>100 confirmations)
        # - a descendants of non-final and non-mature outputs.
        # - if the re-org has been deep enough that the disconnect pool has filled up
        # - if the standardness or consensus rules have changed across the reorg
        # - and probably more...
        # We only test the non-final case.
        self.log.info("Testing removal reason REORG (tx non-final after reorg)")

        # create an output to spend from
        address = node.getnewaddress()
        included_in_block_txid = node.sendtoaddress(address, 1.0)
        tip = node.generatetoaddress(1, ADDRESS_BCRT1_UNSPENDABLE)[0]
        # discard zmq messages for removed tx for block inclusion
        subscriber.discard_mempoolremoved_message_block()

        # spend output from tx from the just mined block
        vout = find_vout_for_address(node, included_in_block_txid, address)
        inputs = [{'txid': included_in_block_txid, 'vout': vout}]
        outputs = {node.getnewaddress(): 0.99}
        # set a locktime of the current height
        locktime = node.getblockcount()
        raw = node.createrawtransaction(inputs, outputs, locktime)
        signed = node.signrawtransactionwithwallet(raw)["hex"]
        mempool_to_be_reorged_txid = node.sendrawtransaction(signed)

        # invalidate the mined block
        node.invalidateblock(tip)

        # The ZMQ interface should receive the transaction that is reorged as
        # the transaction is not final anymore
        expected = {mempool_to_be_reorged_txid: "REORG"}
        subscriber.check_mempoolremoved_messages(expected)

        # The mempool should now contain the 'included_in_block_txid' tx
        assert_equal(True, included_in_block_txid in node.getrawmempool())

if __name__ == '__main__':
    ZMQTest().main()
