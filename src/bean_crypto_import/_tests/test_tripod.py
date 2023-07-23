from decimal import Decimal
import sys
from bean_crypto_import.tripod import Tripod

import pytest

# Valid initialization

def test_valid_transaction():
    tripod = Tripod(rcvd_amt="1.0", rcvd_cur="BTC",
                    sent_amt="10000.0", sent_cur="USDT",
                    fees_amt="10.0", fees_cur="USD")
    assert tripod.rcvd_amt == Decimal("1.0")
    assert tripod.rcvd_cur == "BTC"
    assert tripod.sent_amt == Decimal("10000.0")
    assert tripod.sent_cur == "USDT"
    assert tripod.fees_amt == Decimal("10.0")
    assert tripod.fees_cur == "USD"

def test_valid_send():
    tripod = Tripod(rcvd_amt="", rcvd_cur="",
                    sent_amt="100.0", sent_cur="USDT",
                    fees_amt="1.0", fees_cur="USD")
    
    assert tripod.is_transfer()
    assert tripod.amount() == Decimal("100.0")
    assert tripod.currency() == "USDT"

def test_valid_receive():
    tripod = Tripod(rcvd_amt="10.0", rcvd_cur="BTC",
                    sent_amt="", sent_cur="",
                    fees_amt="1.0", fees_cur="USD")
    
    assert tripod.is_transfer()
    assert tripod.amount() == Decimal("10.0")
    assert tripod.currency() == "BTC"

# Invalid initialization

def test_reject_missing_field_of_leg():
    with pytest.raises(Exception):
        tripod = Tripod(rcvd_amt="", rcvd_cur="BTC",
                        sent_amt="10000.0", sent_cur="USDT",
                        fees_amt="10.0", fees_cur="USD")
    with pytest.raises(Exception):
        tripod = Tripod(rcvd_amt="1.0", rcvd_cur="",
                        sent_amt="10000.0", sent_cur="USDT",
                        fees_amt="10.0", fees_cur="USD")
    with pytest.raises(Exception):
        tripod = Tripod(rcvd_amt="1.0", rcvd_cur="BTC",
                        sent_amt="", sent_cur="USDT",
                        fees_amt="10.0", fees_cur="USD")
    with pytest.raises(Exception):
        tripod = Tripod(rcvd_amt="1.0", rcvd_cur="BTC",
                        sent_amt="10000.0", sent_cur="",
                        fees_amt="10.0", fees_cur="USD")
    with pytest.raises(Exception):
        tripod = Tripod(rcvd_amt="1.0", rcvd_cur="BTC",
                        sent_amt="10000.0", sent_cur="USDT",
                        fees_amt="", fees_cur="USD")
    with pytest.raises(Exception):
        tripod = Tripod(rcvd_amt="1.0", rcvd_cur="BTC",
                        sent_amt="10000.0", sent_cur="USDT",
                        fees_amt="10.0", fees_cur="")

def test_reject_negative_amounts():
    with pytest.raises(Exception):
        tripod = Tripod(rcvd_amt="-1.0", rcvd_cur="BTC",
                        sent_amt="10000.0", sent_cur="USDT",
                        fees_amt="10.0", fees_cur="USD")
    with pytest.raises(Exception):
        tripod = Tripod(rcvd_amt="1.0", rcvd_cur="BTC",
                        sent_amt="-10000.0", sent_cur="USDT",
                        fees_amt="10.0", fees_cur="USD")
    with pytest.raises(Exception):
        tripod = Tripod(rcvd_amt="-1.0", rcvd_cur="BTC",
                        sent_amt="10000.0", sent_cur="USDT",
                        fees_amt="-10.0", fees_cur="USD")

def test_reject_fee_only():
    with pytest.raises(Exception):
        tripod = Tripod(fees_amt="10.0", fees_cur="")

def test_reject_for_self_transaction():
    with pytest.raises(Exception):
        tripod = Tripod(rcvd_amt="1.0", rcvd_cur="BTC",
                        sent_amt="1.0", sent_cur="BTC",
                        fees_amt="10.0", fees_cur="USD")

# Other logic

def test_is_transaction():
    tripod = Tripod(rcvd_amt="1.0", rcvd_cur="BTC",
                    sent_amt="10000.0", sent_cur="USDT",
                    fees_amt="10.0", fees_cur="USD")
    assert tripod.is_transaction()
    assert not tripod.is_transfer()
    assert tripod.tx_class() == "Transaction"

def test_is_send():
    tripod = Tripod(rcvd_amt="", rcvd_cur="",
                    sent_amt="100.0", sent_cur="USDT",
                    fees_amt="1.0", fees_cur="USD")
    assert tripod.is_transfer()
    assert tripod.is_send()
    assert not tripod.is_receive()
    assert tripod.tx_class() == "Send"

def test_is_receive():
    tripod = Tripod(rcvd_amt="10.0", rcvd_cur="BTC",
                    sent_amt="", sent_cur="",
                    fees_amt="1.0", fees_cur="USD")
    assert tripod.is_transfer()
    assert tripod.is_receive()
    assert not tripod.is_send()
    assert tripod.tx_class() == "Receive"

def test_xfer_cur():
    tripod = Tripod(rcvd_amt="", rcvd_cur="",
                    sent_amt="100.0", sent_cur="USDT",
                    fees_amt="1.0", fees_cur="USD")
    assert tripod.xfer_cur() == "USDT"
    tripod = Tripod(rcvd_amt="1.0", rcvd_cur="BTC",
                    sent_amt="", sent_cur="",
                    fees_amt="1.0", fees_cur="USD")
    assert tripod.xfer_cur() == "BTC"

# TODO
# def test_impute_price():
#     tripod = Tripod(rcvd_amt="1.0", rcvd_cur="BTC",
#                     sent_amt="10000.0", sent_cur="USDT",
#                     fees_amt="10.0", fees_cur="USD")
#     assert tripod.imputed_price("USDT") == Decimal("10000.0")
#     assert tripod.imputed_price("BTC") == Decimal("1.0")