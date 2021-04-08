#!/usr/bin/env python3
# Copyright (c) 2015-2019 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test the ZMQ publisher mempoolremoved to notify us on a transaction that
was removed from the the mempool due to a conflict with an in-block
transaction"""

import zmq
from time import sleep
from random import randint

from test_framework.address import ADDRESS_BCRT1_UNSPENDABLE
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal, connect_nodes, find_vout_for_address, disconnect_nodes
from test_framework.util_patched_zmq import ZMQSubscriber, removalReason

class ZMQTest (BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 2

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

    def receive_removed_transaction(self, zmq_subscriber):
        # Should receive a payload with two elements (rawtx, removal reason)
        payload = zmq_subscriber.receive_multi_payload()
        assert_equal(2, len(payload))

        # First payload element should be the raw transaction
        rawtx = payload[0]
        tx = CTransaction()
        tx.deserialize(BytesIO(rawtx))
        tx.calc_sha256()

        # Second payload element should be the removal reason
        reason = struct.unpack('<I', payload[1])[-1]

        return [tx.hash, reason]

    def test_mempool_removed(self):
        address = 'tcp://127.0.0.1:{}'.format(randint(20000, 50000))
        socket = self.ctx.socket(zmq.SUB)
        socket.set(zmq.RCVTIMEO, 60000)
        topic = b"mempoolremoved"

        arg_zmq_mempoolremoved = "-zmqpub%s=%s" % (topic.decode(), address)
        arg_txindex = "-txindex=1"

        node0 = self.nodes[0]
        node1 = self.nodes[1]

        subscriber = ZMQSubscriber(socket, topic)
        self.restart_node(0, [arg_txindex, arg_zmq_mempoolremoved])
        sleep(0.2)
        socket.connect(address)

        self.log.info("Testing mempoolremoved CONFLICT")
        connect_nodes(node0, 1)
        self.sync_all()

        # create an utxo that the in-block and the in-mempool transaction
        # will spend
        utxo_address = node0.getnewaddress()
        utxo_txid = node0.sendtoaddress(utxo_address, 1.0)
        node0.generatetoaddress(1, ADDRESS_BCRT1_UNSPENDABLE)
        # discard zmq messages for removed tx for block inclusion
        subscriber.discard_mempoolremoved_message_block()

        # create two different transactions spending the same UTXO
        txns = []
        vout = find_vout_for_address(node0, utxo_txid, utxo_address)
        inputs = [{'txid': utxo_txid, 'vout': vout}]
        for _ in range(2):
            outputs = {node0.getnewaddress(): 0.99}
            raw = node0.createrawtransaction(inputs, outputs)
            signed = node0.signrawtransactionwithwallet(raw)["hex"]
            txns.append(signed)

        # disconnect the nodes
        self.sync_all()
        disconnect_nodes(node0, 1)
        self.log.info("Nodes disconnected")

        # node1: broadcast the first tx and then mine a block on
        node1.sendrawtransaction(txns[0])
        node1.generatetoaddress(1, ADDRESS_BCRT1_UNSPENDABLE)[0]

        # node0: broadcast the in-mempool tx
        inmempool_txid = node0.sendrawtransaction(txns[1])

        # re-connect the nodes
        connect_nodes(node0, 1)

        # The ZMQ interface should receive the in-mempool tx that conflicts
        # with the in-block transaction
        expected = {inmempool_txid: 'CONFLICT'}
        subscriber.check_mempoolremoved_messages(expected)


if __name__ == '__main__':
    ZMQTest().main()
