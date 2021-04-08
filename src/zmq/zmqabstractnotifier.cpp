// Copyright (c) 2015-2019 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <zmq/zmqabstractnotifier.h>

#include <cassert>

#include <txmempool.h>

const int CZMQAbstractNotifier::DEFAULT_ZMQ_SNDHWM;

CZMQAbstractNotifier::~CZMQAbstractNotifier()
{
    assert(!psocket);
}

bool CZMQAbstractNotifier::NotifyBlock(const CBlockIndex * /*CBlockIndex*/)
{
    return true;
}

bool CZMQAbstractNotifier::NotifyTransaction(const CTransaction &/*transaction*/)
{
    return true;
}

bool CZMQAbstractNotifier::NotifyBlockConnect(const CBlockIndex * /*CBlockIndex*/)
{
    return true;
}

bool CZMQAbstractNotifier::NotifyBlockDisconnect(const CBlockIndex * /*CBlockIndex*/)
{
    return true;
}

bool CZMQAbstractNotifier::NotifyTransactionAcceptance(const CTransaction &/*transaction*/, uint64_t mempool_sequence)
{
    return true;
}

bool CZMQAbstractNotifier::NotifyTransactionRemoval(const CTransaction &/*transaction*/, uint64_t mempool_sequence)
{
    return true;
}

bool CZMQAbstractNotifier::NotifyMempoolTransactionAdded(const CTransaction &/*transaction*/, const CAmount/*fee*/)
{
    return true;
}

bool CZMQAbstractNotifier::NotifyMempoolTransactionRemoved(const CTransaction &/*transaction*/, const MemPoolRemovalReason /*reason*/)
{
    return true;
}

bool CZMQAbstractNotifier::NotifyChainBlockConnected(const CBlockIndex * /*CBlockIndex*/)
{
    return true;
}

bool CZMQAbstractNotifier::NotifyMempoolTransactionReplaced(const CTransaction &/*replaced*/, const CAmount/*replaced tx fee*/, const CTransaction &/*replacment*/, const CAmount/*replacement tx fee*/)
{
    return true;
}

bool CZMQAbstractNotifier::NotifyMempoolTransactionConfirmed(const CTransaction &/*transaction*/, const CBlockIndex *)
{
    return true;
}

bool CZMQAbstractNotifier::NotifyChainTipChanged(const CBlockIndex *)
{
    return true;
}

bool CZMQAbstractNotifier::NotifyChainHeaderAdded(const CBlockIndex *)
{
    return true;
}