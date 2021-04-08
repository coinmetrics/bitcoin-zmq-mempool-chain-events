// Copyright (c) 2015-2018 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_ZMQ_ZMQPUBLISHNOTIFIER_H
#define BITCOIN_ZMQ_ZMQPUBLISHNOTIFIER_H

#include <zmq/zmqabstractnotifier.h>

typedef std::vector<unsigned char> zmq_message_part;
typedef std::vector<zmq_message_part> zmq_message;

class CBlockIndex;

class CZMQAbstractPublishNotifier : public CZMQAbstractNotifier
{
private:
    uint32_t nSequence {0U}; //!< upcounting per message sequence number

public:

    /* send zmq multipart message
       parts:
          * command
          * data
          * message sequence number
    */
    bool SendZmqMessage(const char *command, const void* data, size_t size);

    /* sends a zmq multipart message with the following parts:
        * command (aka ZMQ topic)
        * payload (zero, one or multiple payload parts)
        * message sequence number
    */
    bool SendMessage(const char *command, const std::vector<zmq_message_part>& payload);

    bool Initialize(void *pcontext) override;
    void Shutdown() override;
};

class CZMQPublishHashBlockNotifier : public CZMQAbstractPublishNotifier
{
public:
    bool NotifyBlock(const CBlockIndex *pindex) override;
};

class CZMQPublishHashTransactionNotifier : public CZMQAbstractPublishNotifier
{
public:
    bool NotifyTransaction(const CTransaction &transaction) override;
};

class CZMQPublishRawBlockNotifier : public CZMQAbstractPublishNotifier
{
public:
    bool NotifyBlock(const CBlockIndex *pindex) override;
};

class CZMQPublishRawTransactionNotifier : public CZMQAbstractPublishNotifier
{
public:
    bool NotifyTransaction(const CTransaction &transaction) override;
};

class CZMQPublishSequenceNotifier : public CZMQAbstractPublishNotifier
{
public:
    bool NotifyBlockConnect(const CBlockIndex *pindex) override;
    bool NotifyBlockDisconnect(const CBlockIndex *pindex) override;
    bool NotifyTransactionAcceptance(const CTransaction &transaction, uint64_t mempool_sequence) override;
    bool NotifyTransactionRemoval(const CTransaction &transaction, uint64_t mempool_sequence) override;
};

class CZMQPublishMempolAddedNotifier : public CZMQAbstractPublishNotifier
{
public:
    bool NotifyMempoolTransactionAdded(const CTransaction &transaction, const CAmount fee) override;
};

class CZMQPublishMempoolRemovedNotifier : public CZMQAbstractPublishNotifier
{
public:
    bool NotifyMempoolTransactionRemoved(const CTransaction &transaction, const MemPoolRemovalReason reason) override;
};

class CZMQPublishChainConnectedNotifier : public CZMQAbstractPublishNotifier
{
public:
    bool NotifyChainBlockConnected(const CBlockIndex *pindex) override;
};

class CZMQPublishMempolReplacedNotifier : public CZMQAbstractPublishNotifier
{
public:
    bool NotifyMempoolTransactionReplaced(const CTransaction& replaced, const CAmount replaced_tx_fee, const CTransaction& replacement, const CAmount replacement_tx_fee) override;
};

class CZMQPublishMempoolConfirmedNotifier : public CZMQAbstractPublishNotifier
{
public:
    bool NotifyMempoolTransactionConfirmed(const CTransaction &transaction, const CBlockIndex *pindex) override;
};

class CZMQPublishChainTipChangedNotifier : public CZMQAbstractPublishNotifier
{
public:
    bool NotifyChainTipChanged(const CBlockIndex *pindex) override;
};

class CZMQPublishChainHeaderAddedNotifier : public CZMQAbstractPublishNotifier
{
public:
    bool NotifyChainHeaderAdded(const CBlockIndex *pindexHeader) override;
};

#endif // BITCOIN_ZMQ_ZMQPUBLISHNOTIFIER_H
