import copy
from datetime import datetime
import sys
import beancount

from beancount.core import amount, data
from beancount.core.number import D
from magicbeans import common
from beancount.parser import parser
from beancount.parser import printer
from beancount.core.data import Transaction
import dateutil.parser
import pytest

from magicbeans.transfers import Network, Link


def test_rounded_amt() -> None:
    assert (common.rounded_amt(D("7.123456789"), "USD", 2)
            == amount.Amount(D("7.12"), "USD"))
    assert (common.rounded_amt(D("7.123456789"), "USD")
            == amount.Amount(D("7.1235"), "USD"))
    assert (common.rounded_amt(D("7.123456789"), "USDT")
            == amount.Amount(D("7.12345679"), "USDT"))
    assert (common.rounded_amt(D("7.123456789"), "BTC")
            == amount.Amount(D("7.123456789"), "BTC"))


def EmptyCost():
    return data.Cost(None, None, None, None)

def get_tx_notimestamp() -> Transaction:
    entries, errors, options = parser.parse_string("""
    2020-01-05 * "CBP: Buy 1.10 BTC"                       
      orderid: "47ac3b7d-f812-ac2bdff39-00fd1535bc8a"                    
      Assets:Coinbase:BTC           1.1 BTC {1000.00 USD}
      Assets:Coinbase:USD       -1105.0 USD               
      Expenses:Financial:Fees       5.0 USD               
    """)
    return entries[0]

def test_attach_timestamp_unaware() -> None:
    tx: Transaction = get_tx_notimestamp()
    naive_ts = "2020-01-05T16:12:51.376"
    timestamp = dateutil.parser.isoparse(naive_ts)
    with pytest.raises(Exception):
        common.attach_timestamp(tx, timestamp)

def test_attach_timestamp() -> None:
    tx: Transaction = get_tx_notimestamp()
    iso_ts = "2020-01-05T16:12:51.376Z"
    timestamp = dateutil.parser.isoparse(iso_ts)
    common.attach_timestamp(tx, timestamp)

    assert tx.meta["timestamp"] == iso_ts

def test_attach_timestamp_ends_in_zeros() -> None:
    tx: Transaction = get_tx_notimestamp()
    iso_ts = "2020-01-05T16:12:00Z"
    timestamp = dateutil.parser.isoparse(iso_ts)
    common.attach_timestamp(tx, timestamp)

    assert tx.meta["timestamp"] == iso_ts


def get_tx_wtimestamp_nofees() -> Transaction:
    entries, errors, options = parser.parse_string("""
    2020-01-05 * "Transfer USDT"                       
      orderid: "47ac3b7d-f812-ac2bdff39-00fd1535bc8a"                    
      timestamp: "2020-01-05T16:12:51.376Z"
      Assets:Binance:USDT        1000.0 USDT
      Assets:Coinbase:USDT      -1000.0 USDT
    """)
    return entries[0]

def get_tx_wtimestamp_wfees() -> Transaction:
    entries, errors, options = parser.parse_string("""
    2020-01-05 * "Transfer USDT"                       
      orderid: "47ac3b7d-f812-ac2bdff39-00fd1535bc8a"                    
      timestamp: "2020-01-05T16:12:51.376Z"
      Assets:Binance:USDT        1000.0 USDT
      Assets:Coinbase:USDT      -1000.0 USDT
      Assets:Coinbase:USDT        -10.1010101 USDT {} @ 0.99 USD
        is_fee: TRUE
      Expenses:Fees                10.0 USD
        is_fee: TRUE
      Income:PnL
        is_fee: TRUE                                                    
    """)
    return entries[0]

def test_split_out_marked_fees_noop() -> None:
    original_tx = get_tx_wtimestamp_nofees()
    (nonfee_tx, fee_tx) = common.split_out_marked_fees(original_tx, "Income:PnL")
    assert nonfee_tx == None
    assert fee_tx == None

def test_split_out_marked_fees_dosplit() -> None:
    original_tx = get_tx_wtimestamp_wfees()
    (nonfee_tx, fee_tx) = common.split_out_marked_fees(original_tx, "Income:PnL")
    assert (printer.format_entry(nonfee_tx) ==
            '2020-01-05 * "Transfer USDT"\n'
            '  orderid: "47ac3b7d-f812-ac2bdff39-00fd1535bc8a"\n'
            '  timestamp: "2020-01-05T16:12:51.376Z"\n'
            '  Assets:Binance:USDT    1000.0 USDT\n'
            '  Assets:Coinbase:USDT  -1000.0 USDT\n')

    assert (printer.format_entry(fee_tx) ==
            '2020-01-05 * "Fees for Transfer USDT"\n'
            '  orderid: "47ac3b7d-f812-ac2bdff39-00fd1535bc8a"\n'
            '  timestamp: "2020-01-05T16:12:51.377Z"\n'
            '  Assets:Coinbase:USDT  -10.1010101 USDT {} @ 0.99 USD\n'
            '    is_fee: TRUE\n'
            '  Expenses:Fees                10.0 USD\n'
            '    is_fee: TRUE\n'
            '  Income:PnL\n'
            '    is_fee: TRUE\n')

