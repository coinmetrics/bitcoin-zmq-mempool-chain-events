# Patch: Mempool and Chain event publishers for ZMQ

This is a patch-set to Bitcoin Core that adds more functionality to the ZMQ interface.
While the patches does not touch consensus or wallet code, it's not recommended to use this node in a consensus critical environment where user
funds are at risk.

## Changes:

### add: multi-payload ZMQ multipart messages

A new internal function overwrite for `zmq_send_multipart()` is added.
This allows us to send ZMQ multipart messages with a variable amount (zero to many) of payload parts.

```
ZMQ multipart message structure
Before: | topic | payload | sequence |
After:  | topic | timestamp | payload_0 | payload_1 | ... | payload_n | sequence |
```

This change is backward compatible to the format of the existing ZMQ publishers.
The topic is the first part of the message, a timestamp the second, and the sequence is the last part of the message.

### add: Mempool and Chain events

A new ZMQ publisher with the topic `mempooladded` is added. The command line
option `-zmqpubmempooladded=<address>` sets the address for the publisher and
`-zmqpubmempooladdedhwm=<n>` sets a custom outbound message high water mark. The
publisher notifies when a transaction is added to the mempool after the mempool
is loaded and passes the txid, the raw transaction and the fee paid.

The functional tests for this ZMQ publisher can be run with `python3
test/functional/test_runner.py test/functional/interface_zmq_mempooladd.py`.
Make sure `bitcoind` is compiled with a wallet otherwise the tests are skipped.

```
ZMQ multipart message structure
| topic | timestamp | txid | rawtx | fee | sequence |
```

- `topic` equals `mempooladded`
- `timestamp` are the milliseconds since 01/01/1970 as int64 in Little Endian
- `txid` is the transaction id
- `rawtx` is a serialized Bitcoin transaction
- `fee` is a `int64` in Little Endian
- `sequence` is a `uint32` in Little Endian

#### Mempool-remove event with removal reason

A new ZMQ publisher with the topic `mempoolremoved` is added. The command line
option `-zmqpubmempoolremoved=<address>` sets the address for the publisher and
`-zmqpubmempoolremovedhwm=<n>` sets a custom outbound message high water mark.
The publisher notifies when a transaction is removed from the mempool and passes
the txid, the raw transaction, and the removal reason.

| Value | Name | Description |
|:-----:|:----------:|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 0 | Expiry | Transactions in the Mempool can expire. The default expiry timeout is 336 hours (2 weeks). |
| 1 | Size limit | As the internal data structure storing the Mempool gets close to `maxmempool` (default 300MB) low feerate transactions are evicted. |
| 2 | Reorg | Transactions that become invalid after a reorg are evicted. Note: Often transactions are still valid after a reorg. A transaction that might become valid is, for example, a transaction that spends a now not-mature coinbase output. |
| 3 | Block | Transactions included in a block of the most-work chain are removed from the Mempool. |
| 4 | Conflict | Transactions conflicting with an in-block transaction are removed. |
| 5 | Replaced | Transactions that are replaced are removed from the Mempool.  |                                                                                                                                                                      |

The functional tests for this ZMQ publisher can be run with `python3
test/functional/test_runner.py test/functional/interface_zmq_mempoolremove*`.
Make sure `bitcoind` is compiled with a wallet otherwise the tests are skipped.

```
ZMQ multipart message structure
| topic | timestamp | txid | rawtx | removal reason | sequence |
```

- `topic` equals `mempoolremoved`
- `timestamp` are the milliseconds since 01/01/1970 as int64 in Little Endian
- `txid` is the transaction id
- `rawtx` is a serialized Bitcoin transaction
- `removal reason` is an `int` in Little Endian
- `sequence` is an `uint32` in Little Endian

#### Mempool-replaced event with both transactions

A new ZMQ publisher with the topic `mempoolreplaced` is added. The command-line
option `-zmqpubmempoolreplaced=<address>` sets the address for the publisher and
`-zmqpubmempoolreplacedhwm=<n>` sets a custom outbound message high water mark.
The publisher notifies when a transaction in the mempool is replaced. This
includes both the transaction id and raw transaction of the replaced and the
replacement transaction as well as their fees.

The functional tests for this ZMQ publisher can be run with `python3
test/functional/test_runner.py interface_zmq_mempoolreplace.py`.

```
ZMQ multipart message structure
| topic | timestamp | txid replaced | rawtx replaced | fee replaced | txid replacement | rawtx replacement | fee replacement | sequence |
```

- `topic` equals `mempoolreplaced`
- `timestamp` are the milliseconds since 01/01/1970 as int64 in Little Endian
- `txid replaced` is the txid of the replaced transaction
- `rawtx replaced` is the serialized Bitcoin transaction that is replaced
- `fee replaced` is the fee of the replaced transaction as a `int64_t` in Little Endian
- `txid replacement` is the txid of the replacement transaction
- `rawtx replacement` is the serialized Bitcoin transaction that is the replacement
- `fee replacement` is the fee of the replacement transaction as a `int64_t` in Little Endian
- `sequence` is an `uint32` in Little Endian

#### Mempool-confirmed event with block header and height

A new ZMQ publisher with the topic `mempoolconfirmed` is added. The command line
option `-zmqpubmempoolconfirmed=<address>` sets the address for the publisher
and `-zmqpubmempoolconfirmedhwm=<n>` sets a custom outbound message high water
mark. The publisher notifies when a transaction is included in a block and
passes the txid, the raw transaction, the block height and the block hash.

The functional tests for this ZMQ publisher can be run with `python3
test/functional/test_runner.py
test/functional/interface_zmq_mempoolconfirmed.py`. Make sure bitcoind is
compiled with a wallet otherwise the tests are skipped.

```
ZMQ multipart message structure
| topic | timestamp | txid | rawtx | block height | block hash | header | sequence |
```

- `topic` equals `mempoolconfirmed`
- `timestamp` are the milliseconds since 01/01/1970 as int64 in Little Endian
- `txid` is the transaction id
- `rawtx` is a serialized Bitcoin transaction
- `block height` is the block height as `int32` in Little Endian
- `block hash` is the block hash
- `header` is the 80-byte serialized block header
- `sequence` is a `uint32` in Little Endian

#### Chain-tipchanged event with height and header

A new ZMQ publisher with the topic `chaintipchanged` is added. The command-line
option `-zmqpubchaintipchanged=<address>` sets the address for the publisher and
`-zmqpubchaintipchangedhwm=<n>` sets a custom outbound message high water mark.
The publisher notifies when a block is connected to a branch on a chain. Note:
This block does not need to be the the most-work chain.

The functional tests for this ZMQ publisher can be run with `python3
test/functional/test_runner.py interface_zmq_chaintipchanged.py`.

#### Specification
```
ZMQ multipart message structure
| topic | timestamp | hash | height | header | sequence |
```

- `topic` equals `chaintipchanged`
- `timestamp` are the milliseconds since 01/01/1970 as int64 in Little Endian
- `hash` is the block hash
- `height` is the block height as `int32` in Little Endian
- `header` is the 80-byte serialized block header
- `sequence` is an `uint32` in Little Endian

#### Chain-headeradded event with height and header

A new ZMQ publisher with the topic `chainheaderadded` is added. The command-line
option `-zmqpubchainheaderadded=<address>` sets the address for the publisher
and `-zmqpubchainheaderaddedhwm=<n>` sets a custom outbound message high water
mark. The publisher notifies when a header is connected to a branch on a chain.
Note: This header addition does not need to be on the the most-work chain.

The functional tests for this ZMQ publisher can be run with `python3
test/functional/test_runner.py interface_zmq_chainheaderadded.py`.

```
ZMQ multipart message structure
| topic | timestamp | hash | height | header | sequence |
```

- `topic` equals `chainheaderadded`
- `timestamp` are the milliseconds since 01/01/1970 as int64 in Little Endian
- `hash` is the block hash
- `height` is the block height as `int32` in Little Endian
- `header` is the 80-byte serialized block header
- `sequence` is an `uint32` in Little Endian

#### Chain-connected event with raw block

A new ZMQ publisher with the topic `chainconnected` is added. The command-line
option `-zmqpubchainconnected=<address>` sets the address for the publisher and
`-zmqpubchainconnectedhwm=<n>` sets a custom outbound message high water mark.
The publisher notifies when a block is connected to a branch on a chain. Note:
This block does not need to be the the most-work chain.

The functional tests for this ZMQ publisher can be run with `python3
test/functional/test_runner.py interface_zmq_chainblockconnected.py`.

```
ZMQ multipart message structure
| topic | timestamp | hash | height | prev hash | rawblock | sequence |
```

- `topic` equals `chainconnected`
- `timestamp` are the milliseconds since 01/01/1970 as int64 in Little Endian
- `hash` is the block hash
- `height` is the block height as `int32` in Little Endian
- `prev hash` is the previous block hash
- `block` is a serialized Bitcoin block
- `sequence` is an `uint32` in Little Endian

### change: increase default ZMQ high water mark

The previous default of 1.000 did (correctly) drop messages when, for
example, broadcasting many mempoolconfirmed or mempoolremoved messages.

The high water mark is increased to 100.000. No more messages should
be dropped.
