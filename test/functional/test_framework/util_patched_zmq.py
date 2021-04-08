#!/usr/bin/env python3
"""Utility functionality for the patched ZMQ interface."""

import struct
import time
from io import BytesIO

import zmq

from test_framework.messages import COutPoint, CTransaction
from test_framework.util import assert_equal

removalReason = {
    'EXPIRY': 0,
    'SIZELIMIT': 1,
    'REORG': 2,
    'BLOCK': 3,
    'CONFLICT': 4,
    'REPLACED': 5,
}

class ZMQSubscriber:
    def __init__(self, socket, topic):
        self.sequence = 0
        self.socket = socket
        self.topic = topic
        self.socket.setsockopt(zmq.SUBSCRIBE, self.topic)

    def receive_multi_payload(self):
        """receives a multipart zmq message with zero, one or multiple payloads
        and checks the topic and sequence number"""
        msg = self.socket.recv_multipart()


        # Message should consist of at least three parts
        # (topic, timestamp and sequence)
        assert(len(msg) >= 3)
        topic = msg[0]
        timestamp = msg[1]
        sequence = msg[-1]

        # Topic should match the subscriber topic.
        assert_equal(topic, self.topic)

        # Timestamp should be roughly in the range of the current timestamp.
        timestamp = struct.unpack('<q', timestamp)[-1]
        timestamp = timestamp / 1000 # convert to seconds
        diff_seconds = time.time() - timestamp
        assert diff_seconds < 5 # seconds
        assert diff_seconds > -5 # seconds

        # Sequence should be incremental.
        assert_equal(struct.unpack('<I', sequence)[-1], self.sequence)
        self.sequence += 1
        return msg[2:-1]

    def receive_mempoolremoved_message(self):
        """Retrieves a two-payload ZMQ message from the topic mempoolremoved
        containing the rawtransaction and the removal reason and returns the txid
        and the removal reason"""
        assert_equal(self.topic, b'mempoolremoved')

                # Should receive a payload with three elements (txid, rawtx, removal reason)
        payload = self.receive_multi_payload()
        assert_equal(3, len(payload))

        # First payload element should be the txid
        r_txid = payload[0]

        # Second payload element should be the raw transaction
        r_rawtx = payload[1]
        tx = CTransaction()
        tx.deserialize(BytesIO(r_rawtx))
        tx.calc_sha256()
        assert_equal(r_txid.hex(), tx.hash)

        # Second payload element should be the removal reason
        reason = struct.unpack('<i', payload[2])[-1]

        return [tx.hash, reason]

    def discard_mempoolremoved_message_block(self):
        """Retrieves one ZMQ message from the subscriber and checks that
        it's a transaction removed from the mempool because it confirmed in a
        block and discards it."""

        assert_equal(self.topic, b'mempoolremoved')
        _, reason = self.receive_mempoolremoved_message()
        assert_equal(removalReason["BLOCK"], reason)

    def check_mempoolremoved_messages(self, expected):
        """checks that the in 'expected' defined txid-reason tuples arrive"""
        for _ in range(len(expected)):
            hash, reason = self.receive_mempoolremoved_message()
            assert_equal(True, hash in expected)
            assert_equal(removalReason[expected[hash]], reason)
            del expected[hash]
        assert_equal(0, len(expected))
