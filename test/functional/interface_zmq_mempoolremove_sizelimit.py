#!/usr/bin/env python3
# Copyright (c) 2015-2019 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test the ZMQ notification mempoolremoved to notify us on a low-fee
transaction that was removed from the the mempool due to size limiting"""

import zmq
from time import sleep
from random import randint

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import create_confirmed_utxos, create_lots_of_big_transactions, gen_return_txouts

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

        arg_zmq_mempoolremoved = "-zmqpub%s=%s" % (topic.decode(), address)

        node0 = self.nodes[0]

        self.log.info("Testing ZMQ publisher mempoolremoved")
        subscriber = ZMQSubscriber(socket, topic)
        self.restart_node(0,["-acceptnonstdtxn=1", "-maxmempool=5", "-spendzeroconfchange=0", arg_zmq_mempoolremoved])
        sleep(0.2)
        socket.connect(address)

        self.log.info("Testing removal reason SIZELIMIT")

        txouts = gen_return_txouts()
        relayfee = node0.getnetworkinfo()['relayfee']
        utxos = create_confirmed_utxos(relayfee, node0, 91)

        self.log.info('Create a mempool tx that will be evicted')
        us0 = utxos.pop()
        inputs = [{ "txid" : us0["txid"], "vout" : us0["vout"]}]
        outputs = {node0.getnewaddress() : 0.0001}
        tx = node0.createrawtransaction(inputs, outputs)
        node0.settxfee(relayfee) # specifically fund this tx with low fee
        txF = node0.fundrawtransaction(tx)
        node0.settxfee(0) # return to automatic fee selection
        txFS = node0.signrawtransactionwithwallet(txF['hex'])
        txid = node0.sendrawtransaction(txFS['hex'])

        base_fee = relayfee*100
        for i in range (3):
            create_lots_of_big_transactions(node0, txouts, utxos[30*i:30*i+30], 30, (i+1)*base_fee)

        self.log.info('The tx should be evicted by now')
        # The ZMQ interface should receive the evicted transaction as the
        # first of multiple evicted transactions
        expected = {txid: "SIZELIMIT"}
        subscriber.check_mempoolremoved_messages(expected)

if __name__ == '__main__':
    ZMQTest().main()
