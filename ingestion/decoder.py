def decode_transfer(log):
    sender = "0x" + log["topics"][1][-40:]
    receiver = "0x" + log["topics"][2][-40:]
    token = log["address"].lower()
    amount_raw = int(log["data"], 16)
    tx_hash = log["transactionHash"].lower()
    log_index = int(log["logIndex"], 16)
    block_number = int(
        log["blockNumber"], 16
    )

    event_id = f"{tx_hash}:{log_index}"
    
    return {
        "event_id": event_id,
        "tx_hash": tx_hash,
        "log_index": log_index,
        "block_number": block_number,
        "from_address": sender.lower(),
        "to_address": receiver.lower(),
        "token_address": token,
        "amount_raw": str(amount_raw)
    }