// Copyright (c) 2015-2020 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <zmq/zmqpublishnotifier.h>

#include <chain.h>
#include <chainparams.h>
#include <rpc/server.h>
#include <streams.h>
#include <util/system.h>
#include <validation.h>
#include <zmq/zmqutil.h>

#include <zmq.h>

#include <cstdarg>
#include <cstddef>
#include <map>
#include <string>
#include <utility>

static std::multimap<std::string, CZMQAbstractPublishNotifier*> mapPublishNotifiers;

static const char *MSG_HASHBLOCK = "hashblock";
static const char *MSG_HASHTX    = "hashtx";
static const char *MSG_RAWBLOCK  = "rawblock";
static const char *MSG_RAWTX     = "rawtx";
static const char *MSG_SEQUENCE  = "sequence";

static const char *MSG_MEMPOOLADDED = "mempooladded";
static const char *MSG_MEMPOOLREMOVED = "mempoolremoved";
static const char *MSG_CHAINCONNECTED = "chainconnected";
static const char *MSG_MEMPOOLREPLACED = "mempoolreplaced";
static const char *MSG_MEMPOOLCONFIRMED = "mempoolconfirmed";
static const char *MSG_CHAINTIPCHANGED = "chaintipchanged";
static const char *MSG_CHAINHEADERADDED = "chainheaderadded";

// Internal function to send multipart message
static int zmq_send_multipart(void *sock, const void* data, size_t size, ...)
{
    va_list args;
    va_start(args, size);

    while (1)
    {
        zmq_msg_t msg;

        int rc = zmq_msg_init_size(&msg, size);
        if (rc != 0)
        {
            zmqError("Unable to initialize ZMQ msg");
            va_end(args);
            return -1;
        }

        void *buf = zmq_msg_data(&msg);
        memcpy(buf, data, size);

        data = va_arg(args, const void*);

        rc = zmq_msg_send(&msg, sock, data ? ZMQ_SNDMORE : 0);
        if (rc == -1)
        {
            zmqError("Unable to send ZMQ msg");
            zmq_msg_close(&msg);
            va_end(args);
            return -1;
        }

        zmq_msg_close(&msg);

        if (!data)
            break;

        size = va_arg(args, size_t);
    }
    va_end(args);
    return 0;
}

static int zmq_send_multipart(void *sock, const zmq_message& message)
{
    for (size_t i = 0; i < message.size(); i++) {
        auto const& part = message[i];
        zmq_msg_t msg;

        int rc = zmq_msg_init_size(&msg, part.size());
        if (rc != 0) {
            zmqError("Unable to initialize ZMQ msg");
            return -1;
        }

        void* buf = zmq_msg_data(&msg);
        std::memcpy(buf, part.data(), part.size());

        rc = zmq_msg_send(&msg, sock, (i < (message.size() - 1)) ? ZMQ_SNDMORE : 0);
        if (rc == -1) {
            zmqError("Unable to send ZMQ msg");
            zmq_msg_close(&msg);
            return -1;
        }

        zmq_msg_close(&msg);
    }

    LogPrint(BCLog::ZMQ, "sent message with %d parts\n", message.size());
    return 0;
}

// converts an uint256 hash into a zmq_message_part (hash is reversed)
static zmq_message_part hashToZMQMessagePart(const uint256 hash) {
    zmq_message_part part_hash;
    for (int i = 31; i >= 0; i--)
        part_hash.push_back(hash.begin()[i]);
    return part_hash;
}

// converts a CTransaction into a zmq_message_part (by serializing it)
static zmq_message_part transactionToZMQMessagePart(const CTransaction& transaction) {
    CDataStream ss_replaced(SER_NETWORK, PROTOCOL_VERSION | RPCSerializationFlags());
    ss_replaced << transaction;
    return zmq_message_part(ss_replaced.begin() , ss_replaced.end());
}

// converts an int64_t into a zmq_message_part
static zmq_message_part int64ToZMQMessagePart(const int64_t val) {
    const size_t size = sizeof(int64_t);
    unsigned char value[size];
    std::memcpy(value, &val, size);
    return zmq_message_part(value, value + size);
}

// converts an int32_t into a zmq_message_part
static zmq_message_part int32ToZMQMessagePart(const int32_t val) {
    const size_t size = sizeof(int32_t);
    unsigned char value[size];
    std::memcpy(value, &val, size);
    return zmq_message_part(value, value + size);
}

// returns the current time in milliseconds as zmq_message_part
static zmq_message_part getCurrentTimeMillis() {
    return zmq_message_part(int64ToZMQMessagePart(GetTimeMillis()));
}

// converts a header into a zmq_message_part
static zmq_message_part headerToZMQMessagePart(const CBlockHeader& header) {
    CDataStream ss_header(SER_NETWORK, PROTOCOL_VERSION | RPCSerializationFlags());
    ss_header << header;
    return zmq_message_part(ss_header.begin() , ss_header.end());
}

bool CZMQAbstractPublishNotifier::Initialize(void *pcontext)
{
    assert(!psocket);

    // check if address is being used by other publish notifier
    std::multimap<std::string, CZMQAbstractPublishNotifier*>::iterator i = mapPublishNotifiers.find(address);

    if (i==mapPublishNotifiers.end())
    {
        psocket = zmq_socket(pcontext, ZMQ_PUB);
        if (!psocket)
        {
            zmqError("Failed to create socket");
            return false;
        }

        LogPrint(BCLog::ZMQ, "zmq: Outbound message high water mark for %s at %s is %d\n", type, address, outbound_message_high_water_mark);

        int rc = zmq_setsockopt(psocket, ZMQ_SNDHWM, &outbound_message_high_water_mark, sizeof(outbound_message_high_water_mark));
        if (rc != 0)
        {
            zmqError("Failed to set outbound message high water mark");
            zmq_close(psocket);
            return false;
        }

        const int so_keepalive_option {1};
        rc = zmq_setsockopt(psocket, ZMQ_TCP_KEEPALIVE, &so_keepalive_option, sizeof(so_keepalive_option));
        if (rc != 0) {
            zmqError("Failed to set SO_KEEPALIVE");
            zmq_close(psocket);
            return false;
        }

        rc = zmq_bind(psocket, address.c_str());
        if (rc != 0)
        {
            zmqError("Failed to bind address");
            zmq_close(psocket);
            return false;
        }

        // register this notifier for the address, so it can be reused for other publish notifier
        mapPublishNotifiers.insert(std::make_pair(address, this));
        return true;
    }
    else
    {
        LogPrint(BCLog::ZMQ, "zmq: Reusing socket for address %s\n", address);
        LogPrint(BCLog::ZMQ, "zmq: Outbound message high water mark for %s at %s is %d\n", type, address, outbound_message_high_water_mark);

        psocket = i->second->psocket;
        mapPublishNotifiers.insert(std::make_pair(address, this));

        return true;
    }
}

void CZMQAbstractPublishNotifier::Shutdown()
{
    // Early return if Initialize was not called
    if (!psocket) return;

    int count = mapPublishNotifiers.count(address);

    // remove this notifier from the list of publishers using this address
    typedef std::multimap<std::string, CZMQAbstractPublishNotifier*>::iterator iterator;
    std::pair<iterator, iterator> iterpair = mapPublishNotifiers.equal_range(address);

    for (iterator it = iterpair.first; it != iterpair.second; ++it)
    {
        if (it->second==this)
        {
            mapPublishNotifiers.erase(it);
            break;
        }
    }

    if (count == 1)
    {
        LogPrint(BCLog::ZMQ, "zmq: Close socket at address %s\n", address);
        int linger = 0;
        zmq_setsockopt(psocket, ZMQ_LINGER, &linger, sizeof(linger));
        zmq_close(psocket);
    }

    psocket = nullptr;
}

bool CZMQAbstractPublishNotifier::SendZmqMessage(const char *command, const void* data, size_t size)
{
    assert(psocket);

    /* send three parts, command & data & a LE 4byte sequence number */
    unsigned char msgseq[sizeof(uint32_t)];
    WriteLE32(&msgseq[0], nSequence);
    int rc = zmq_send_multipart(psocket, command, strlen(command), data, size, msgseq, (size_t)sizeof(uint32_t), nullptr);
    if (rc == -1)
        return false;

    /* increment memory only sequence number after sending */
    nSequence++;

    return true;
}


bool CZMQAbstractPublishNotifier::SendMessage(const char *command, const std::vector<zmq_message_part>& payload)
{
    assert(psocket);

    /*
      create message from multiple parts:
       - first part is the command (or topic)
       - second part is the current timestamp
       - followed by one or multiple payload parts
       - ended by a LE 4 byte sequence number
    */
    std::vector<zmq_message_part> message = {};

    // push topic
    message.push_back(zmq_message_part(command, command + strlen(command)));

    // current timestamp
    message.push_back(getCurrentTimeMillis());

    // push payload
    for (size_t i = 0; i < payload.size(); i++)
        message.push_back(payload[i]);

    // push little endian sequence number
    unsigned char sequenceLE[sizeof(uint32_t)];
    WriteLE32(&sequenceLE[0], nSequence);
    message.push_back(zmq_message_part(sequenceLE, sequenceLE + sizeof(uint32_t)));


    int rc = zmq_send_multipart(psocket, message);
    if (rc == -1)
        return false;

    // increment memory only sequence number after sending
    nSequence++;

    return true;
}

bool CZMQPublishHashBlockNotifier::NotifyBlock(const CBlockIndex *pindex)
{
    uint256 hash = pindex->GetBlockHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish hashblock %s to %s\n", hash.GetHex(), this->address);
    char data[32];
    for (unsigned int i = 0; i < 32; i++)
        data[31 - i] = hash.begin()[i];
    return SendZmqMessage(MSG_HASHBLOCK, data, 32);
}

bool CZMQPublishHashTransactionNotifier::NotifyTransaction(const CTransaction &transaction)
{
    uint256 hash = transaction.GetHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish hashtx %s to %s\n", hash.GetHex(), this->address);
    char data[32];
    for (unsigned int i = 0; i < 32; i++)
        data[31 - i] = hash.begin()[i];
    return SendZmqMessage(MSG_HASHTX, data, 32);
}

bool CZMQPublishRawBlockNotifier::NotifyBlock(const CBlockIndex *pindex)
{
    LogPrint(BCLog::ZMQ, "zmq: Publish rawblock %s to %s\n", pindex->GetBlockHash().GetHex(), this->address);

    const Consensus::Params& consensusParams = Params().GetConsensus();
    CDataStream ss(SER_NETWORK, PROTOCOL_VERSION | RPCSerializationFlags());
    {
        LOCK(cs_main);
        CBlock block;
        if(!ReadBlockFromDisk(block, pindex, consensusParams))
        {
            zmqError("Can't read block from disk");
            return false;
        }

        ss << block;
    }

    return SendZmqMessage(MSG_RAWBLOCK, &(*ss.begin()), ss.size());
}

bool CZMQPublishRawTransactionNotifier::NotifyTransaction(const CTransaction &transaction)
{
    uint256 hash = transaction.GetHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish rawtx %s to %s\n", hash.GetHex(), this->address);
    CDataStream ss(SER_NETWORK, PROTOCOL_VERSION | RPCSerializationFlags());
    ss << transaction;
    return SendZmqMessage(MSG_RAWTX, &(*ss.begin()), ss.size());
}


// TODO: Dedup this code to take label char, log string
bool CZMQPublishSequenceNotifier::NotifyBlockConnect(const CBlockIndex *pindex)
{
    uint256 hash = pindex->GetBlockHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish sequence block connect %s to %s\n", hash.GetHex(), this->address);
    char data[sizeof(uint256)+1];
    for (unsigned int i = 0; i < sizeof(uint256); i++)
        data[sizeof(uint256) - 1 - i] = hash.begin()[i];
    data[sizeof(data) - 1] = 'C'; // Block (C)onnect
    return SendZmqMessage(MSG_SEQUENCE, data, sizeof(data));
}

bool CZMQPublishSequenceNotifier::NotifyBlockDisconnect(const CBlockIndex *pindex)
{
    uint256 hash = pindex->GetBlockHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish sequence block disconnect %s to %s\n", hash.GetHex(), this->address);
    char data[sizeof(uint256)+1];
    for (unsigned int i = 0; i < sizeof(uint256); i++)
        data[sizeof(uint256) - 1 - i] = hash.begin()[i];
    data[sizeof(data) - 1] = 'D'; // Block (D)isconnect
    return SendZmqMessage(MSG_SEQUENCE, data, sizeof(data));
}

bool CZMQPublishSequenceNotifier::NotifyTransactionAcceptance(const CTransaction &transaction, uint64_t mempool_sequence)
{
    uint256 hash = transaction.GetHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish hashtx mempool acceptance %s to %s\n", hash.GetHex(), this->address);
    unsigned char data[sizeof(uint256)+sizeof(mempool_sequence)+1];
    for (unsigned int i = 0; i < sizeof(uint256); i++)
        data[sizeof(uint256) - 1 - i] = hash.begin()[i];
    data[sizeof(uint256)] = 'A'; // Mempool (A)cceptance
    WriteLE64(data+sizeof(uint256)+1, mempool_sequence);
    return SendZmqMessage(MSG_SEQUENCE, data, sizeof(data));
}

bool CZMQPublishSequenceNotifier::NotifyTransactionRemoval(const CTransaction &transaction, uint64_t mempool_sequence)
{
    uint256 hash = transaction.GetHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish hashtx mempool removal %s to %s\n", hash.GetHex(), this->address);
    unsigned char data[sizeof(uint256)+sizeof(mempool_sequence)+1];
    for (unsigned int i = 0; i < sizeof(uint256); i++)
        data[sizeof(uint256) - 1 - i] = hash.begin()[i];
    data[sizeof(uint256)] = 'R'; // Mempool (R)emoval
    WriteLE64(data+sizeof(uint256)+1, mempool_sequence);
    return SendZmqMessage(MSG_SEQUENCE, data, sizeof(data));
}

bool CZMQPublishMempolAddedNotifier::NotifyMempoolTransactionAdded(const CTransaction &transaction, const CAmount fee)
{
    uint256 txid = transaction.GetHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish mempooladded %s\n", txid.GetHex());

    std::vector<zmq_message_part> payload = {};

    // txid
    payload.push_back(hashToZMQMessagePart(txid));

    // raw tx
    payload.push_back(transactionToZMQMessagePart(transaction));

    // fee (as int64_t)
    payload.push_back(int64ToZMQMessagePart(fee));

    return SendMessage(MSG_MEMPOOLADDED, payload);
}

bool CZMQPublishMempoolRemovedNotifier::NotifyMempoolTransactionRemoved(const CTransaction &transaction, const MemPoolRemovalReason reason)
{
    uint256 txid = transaction.GetHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish mempoolremoved %s\n", txid.GetHex());

    std::vector<zmq_message_part> payload = {};

    // txid
    payload.push_back(hashToZMQMessagePart(txid));

    // raw tx
    payload.push_back(transactionToZMQMessagePart(transaction));

    // reason
    unsigned char value[sizeof(reason)];
    std::memcpy(value, &reason, sizeof(value));
    payload.push_back(zmq_message_part(value, value + sizeof(value)));

    return SendMessage(MSG_MEMPOOLREMOVED, payload);
}

bool CZMQPublishMempoolConfirmedNotifier::NotifyMempoolTransactionConfirmed(const CTransaction &transaction, const CBlockIndex *pindex)
{
    uint256 txid = transaction.GetHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish mempoolconfirmed %s\n", txid.GetHex());

    std::vector<zmq_message_part> payload = {};

    // txid
    payload.push_back(hashToZMQMessagePart(txid));

    // raw tx
    payload.push_back(transactionToZMQMessagePart(transaction));

    // block height (as int32_t)
    payload.push_back(int32ToZMQMessagePart(pindex->nHeight));

    // block hash
    payload.push_back(hashToZMQMessagePart(pindex->GetBlockHash()));

    // serialized block header
    payload.push_back(headerToZMQMessagePart(pindex->GetBlockHeader()));

    return SendMessage(MSG_MEMPOOLCONFIRMED, payload);
}

bool CZMQPublishChainConnectedNotifier::NotifyChainBlockConnected(const CBlockIndex *pindex)
{
    uint256 hash = pindex->GetBlockHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish chainconnected %s\n", hash.GetHex());
    std::vector<zmq_message_part> payload = {};

    // hash
    payload.push_back(hashToZMQMessagePart(hash));

    // height (as int32_t)
    payload.push_back(int32ToZMQMessagePart(pindex->nHeight));

    // prev hash
    payload.push_back(hashToZMQMessagePart(pindex->GetBlockHeader().hashPrevBlock));

    const Consensus::Params& consensusParams = Params().GetConsensus();
    CDataStream ss(SER_NETWORK, PROTOCOL_VERSION | RPCSerializationFlags());
    {
        LOCK(cs_main);
        CBlock block;
        if(!ReadBlockFromDisk(block, pindex, consensusParams))
        {
            zmqError("Can't read block from disk");
            return false;
        }

        ss << block;
    }
    payload.push_back(zmq_message_part(ss.begin() , ss.end()));

    return SendMessage(MSG_CHAINCONNECTED, payload);
}


bool CZMQPublishMempolReplacedNotifier::NotifyMempoolTransactionReplaced(const CTransaction &replaced, const CAmount replaced_tx_fee, const CTransaction &replacement, const CAmount replacement_tx_fee)
{
    uint256 replaced_hash = replaced.GetHash();
    uint256 replacement_hash = replacement.GetHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish mempoolreplaced %s by %s\n", replaced_hash.GetHex(), replacement_hash.GetHex());

    std::vector<zmq_message_part> payload = {};

    // replaced txid
    payload.push_back(hashToZMQMessagePart(replaced_hash));

    // replaced raw tx
    payload.push_back(transactionToZMQMessagePart(replaced));

    // fee delta as int64_t
    payload.push_back(int64ToZMQMessagePart(replaced_tx_fee));

    // replacement txid
    payload.push_back(hashToZMQMessagePart(replacement_hash));

    // replacement raw tx
    payload.push_back(transactionToZMQMessagePart(replacement));

    // fee delta as int64_t
    payload.push_back(int64ToZMQMessagePart(replacement_tx_fee));

    return SendMessage(MSG_MEMPOOLREPLACED, payload);
}

bool CZMQPublishChainTipChangedNotifier::NotifyChainTipChanged(const CBlockIndex *pindex)
{
    uint256 hash = pindex->GetBlockHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish chaintipchanged %s\n", hash.GetHex());
    std::vector<zmq_message_part> payload = {};

    // hash
    payload.push_back(hashToZMQMessagePart(hash));

    // height (as int32_t)
    payload.push_back(int32ToZMQMessagePart(pindex->nHeight));

    // serialized block header
    payload.push_back(headerToZMQMessagePart(pindex->GetBlockHeader()));

    return SendMessage(MSG_CHAINTIPCHANGED, payload);
}

bool CZMQPublishChainHeaderAddedNotifier::NotifyChainHeaderAdded(const CBlockIndex *pindex)
{
    uint256 hash = pindex->GetBlockHash();
    LogPrint(BCLog::ZMQ, "zmq: Publish chainheaderadded %s\n", hash.GetHex());
    std::vector<zmq_message_part> payload = {};

    // hash
    payload.push_back(hashToZMQMessagePart(hash));

    // height (as int32_t)
    payload.push_back(int32ToZMQMessagePart(pindex->nHeight));

    // serialized block header
    payload.push_back(headerToZMQMessagePart(pindex->GetBlockHeader()));

    return SendMessage(MSG_CHAINHEADERADDED, payload);
}
