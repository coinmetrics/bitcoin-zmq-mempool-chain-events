#!/usr/bin/env python3
# Copyright (c) 2015-2019 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test the ZMQ publisher chainheaderadded"""
import struct
import zmq

from test_framework.address import ADDRESS_BCRT1_UNSPENDABLE
from test_framework.test_framework import BitcoinTestFramework
from test_framework.messages import CTransaction, hash256
from test_framework.util import assert_equal, connect_nodes, disconnect_nodes
from io import BytesIO
from time import sleep
from random import randint

from test_framework.util_patched_zmq import ZMQSubscriber

def hash256_reversed(byte_str):
    return hash256(byte_str)[::-1]

class ZMQTest (BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 2

    def skip_test_if_missing_module(self):
        self.skip_if_no_py3_zmq()
        self.skip_if_no_bitcoind_zmq()

    def run_test(self):
        import zmq
        self.ctx = zmq.Context()
        try:
            self.test_basic()
            self.test_reorg()
        finally:
            # Destroy the ZMQ context.
            self.log.debug("Destroying ZMQ context")
            self.ctx.destroy(linger=None)

    def test_basic(self):
        import zmq
        address = 'tcp://127.0.0.1:{}'.format(randint(20000, 50000))
        socket = self.ctx.socket(zmq.SUB)
        socket.set(zmq.RCVTIMEO, 2000)
        subscriber = ZMQSubscriber(socket, b'chainheaderadded')

        self.log.info("Test patched chainheaderadded topic")

        # chainheaderadded should notify for every block header added
        self.restart_node(0, ['-zmqpub%s=%s' % (subscriber.topic.decode(), address)])
        socket.connect(address)
        # Relax so that the subscriber is ready before publishing zmq messages
        sleep(0.2)

        lastHeight = self.nodes[0].getblockcount()

        # Generate 3 block in nodes[0] and receive all notifications
        genhashes_node0 = self.nodes[0].generatetoaddress(3, ADDRESS_BCRT1_UNSPENDABLE)
        for block_hash in genhashes_node0:
            hash, height, header = subscriber.receive_multi_payload()
            assert_equal(lastHeight+1, struct.unpack("<I", height)[0])
            assert_equal(block_hash, hash.hex())
            assert_equal(self.nodes[0].getblockheader(hash.hex(), False), header.hex())
            # update last height and hash
            lastHeight += 1

        # allow both nodes to sync
        connect_nodes(self.nodes[0], 1)
        sleep(1)
        disconnect_nodes(self.nodes[0], 1)

    def test_reorg(self):
        import zmq
        address = 'tcp://127.0.0.1:{}'.format(randint(20000, 50000))
        socket = self.ctx.socket(zmq.SUB)
        socket.set(zmq.RCVTIMEO, 1000)
        subscriber = ZMQSubscriber(socket, b'chainheaderadded')

        self.log.info("Reorg testing ZMQ publisher chainheaderadded")

        # chainheaderadded should notify for every block header added
        self.restart_node(0, ['-zmqpub%s=%s' % (subscriber.topic.decode(), address)])
        socket.connect(address)
        # Relax so that the subscriber is ready before publishing zmq messages
        sleep(0.2)

        # make sure nodes are disconnected
        disconnect_nodes(self.nodes[0], 1)

        preForkHeight = self.nodes[0].getblockcount()

        # Generate 6 blocks in nodes[0]
        genhashes_node0 = self.nodes[0].generatetoaddress(6, self.nodes[0].getnewaddress())
        for _ in genhashes_node0:
            _ = subscriber.receive_multi_payload()

        # Generate 3 block in nodes[1]
        genhashes_node1 = self.nodes[1].generatetoaddress(3, self.nodes[1].getnewaddress())

        # Connect nodes[0] to nodes[1]
        connect_nodes(self.nodes[0], 1)

        # Receive header notifications about headers in node0 even if it has a longer chain
        for block_hash in genhashes_node1:
            hash, height, header = subscriber.receive_multi_payload()
            assert_equal(preForkHeight+1, struct.unpack("<I", height)[0])
            assert_equal(block_hash, hash.hex())
            assert_equal(self.nodes[0].getblockheader(hash.hex(), False), header.hex())
            # update last height and hash
            preForkHeight += 1

if __name__ == '__main__':
    ZMQTest().main()
