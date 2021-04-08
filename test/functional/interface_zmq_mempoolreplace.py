#!/usr/bin/env python3
# Copyright (c) 2015-2019 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test the ZMQ publisher mempoolremoved to notify us on a transaction that
was replaced by another."""


import struct
from io import BytesIO
from time import sleep, time
from random import randint

from feature_rbf import make_utxo, txToHex
from test_framework.address import ADDRESS_BCRT1_UNSPENDABLE
from test_framework.messages import (
    COIN,
    COutPoint,
    CTransaction,
    CTxIn,
    CTxOut
)
from test_framework.script import CScript
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import (assert_equal, assert_raises_rpc_error,connect_nodes, find_vout_for_address)
from test_framework.util_patched_zmq import ZMQSubscriber, removalReason


class ZMQTest (BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 1
        self.extra_args = [["-acceptnonstdtxn=1"]]

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
        import zmq
        address = 'tcp://127.0.0.1:{}'.format(randint(20000, 50000))
        socket = self.ctx.socket(zmq.SUB)
        socket.set(zmq.RCVTIMEO, 60000)
        topic = b"mempoolreplaced"

        arg_zmq_mempoolreplaced = "-zmqpub%s=%s" % (topic.decode(), address)
        arg_accept_non_standard = "-acceptnonstdtxn=1"

        node = self.nodes[0]

        # create utxo set before we start to listen on mempoolreplaced
        utxo_value = 1.1*COIN
        utxo_test_removal_replaced = make_utxo(node, int(utxo_value))

        self.log.info("Testing ZMQ publisher mempoolreplaced")
        subscriber = ZMQSubscriber(socket, topic)
        self.restart_node(0, [arg_accept_non_standard, arg_zmq_mempoolreplaced])
        # Relax so that the subscriber is ready before publishing zmq messages
        sleep(0.2)
        socket.connect(address)

        self.log.info("Testing removal reason REPLACED")
        # create transaction that will be replaced
        replaced = CTransaction()
        replaced.vin = [CTxIn(utxo_test_removal_replaced, nSequence=0)]
        replaced.vout = [CTxOut(1 * COIN, CScript([b'a' * 35]))]
        replaced_hex = txToHex(replaced)
        replaced_txid = node.sendrawtransaction(replaced_hex, 0)

        # create replacement transaction with an extra 0.1 BTC in fees
        replacement = CTransaction()
        replacement.vin = [CTxIn(utxo_test_removal_replaced, nSequence=0)]
        replacement.vout = [CTxOut(int(0.9 * COIN), CScript([b'b' * 35]))]
        replacement_hex = txToHex(replacement)
        replacement_txid = node.sendrawtransaction(replacement_hex, 0)

        # The ZMQ interface should receive the replaced notification
        r_replaced_txid, r_replaced_rawtx, r_replaced_tx_fee, r_replacement_txid, r_replacement_rawtx, r_replacement_tx_fee = subscriber.receive_multi_payload()
        assert_equal(replaced_txid, r_replaced_txid.hex())
        assert_equal(replaced_hex, r_replaced_rawtx.hex())
        assert_equal(int(utxo_value) - replaced.vout[0].nValue, int(struct.unpack("<q", r_replaced_tx_fee)[0]))
        assert_equal(replacement_txid, r_replacement_txid.hex())
        assert_equal(replacement_hex, r_replacement_rawtx.hex())
        assert_equal(int(utxo_value) - replacement.vout[0].nValue, int(struct.unpack("<q", r_replacement_tx_fee)[0]))

if __name__ == '__main__':
    ZMQTest().main()
