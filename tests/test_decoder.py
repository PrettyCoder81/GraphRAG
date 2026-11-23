import pytest
from decimal import Decimal
from app.decoder import (
    TRANSFER_TOPIC,
    decode_transfer_log,
    scale_amount,
    normalize_address,
    decode_topic_address,
)


def enc_topic(address):
    return "0x" + ("0" * 24) + address[2:].lower()


def base_log():
    token = "0x" + "1" * 40
    sender = "0x" + "2" * 40
    receiver = "0x" + "3" * 40
    return {
        "transactionHash": "0x" + "a" * 64,
        "logIndex": "0x2",
        "blockNumber": "0x10",
        "blockHash": "0x" + "b" * 64,
        "transactionIndex": "0x1",
        "address": token,
        "topics": [TRANSFER_TOPIC, enc_topic(sender), enc_topic(receiver)],
        "data": "0x" + format(1234567, "064x"),
    }


def test_decode_standard_transfer_log():
    decoded = decode_transfer_log(base_log())
    assert decoded["from_address"] == "0x" + "2" * 40
    assert decoded["to_address"] == "0x" + "3" * 40
    assert decoded["amount_raw"] == "1234567"
    assert decoded["event_id"] == "0x" + "a" * 64 + ":2"
    assert decoded["transaction_index"] == 1


def test_decode_nonstandard_indexed_amount_layout():
    log = base_log()
    log["topics"].append("0x" + format(1234567, "064x"))
    log["data"] = "0x"
    decoded = decode_transfer_log(log)
    assert decoded["amount_raw"] == "1234567"


def test_rejects_empty_data_without_indexed_amount():
    log = base_log()
    log["data"] = "0x"
    with pytest.raises(ValueError, match="one 32-byte hex word"):
        decode_transfer_log(log)


def test_rejects_extra_data_in_unsupported_layout():
    log = base_log()
    log["data"] = "0x" + ("00" * 64)
    with pytest.raises(ValueError, match="exactly one 32-byte hex word"):
        decode_transfer_log(log)


def test_rejects_wrong_event_signature():
    log = base_log()
    log["topics"][0] = "0x" + "f" * 64
    with pytest.raises(ValueError, match="event signature"):
        decode_transfer_log(log)


def test_scale_amount_is_exact_decimal():
    assert scale_amount("1234500", 6) == Decimal("1.2345")


def test_normalize_rejects_bad_address():
    with pytest.raises(ValueError):
        normalize_address("not-an-address")


def test_topic_address():
    address = "0x" + "c" * 40
    assert decode_topic_address(enc_topic(address)) == address
