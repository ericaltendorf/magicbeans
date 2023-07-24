from datetime import datetime
import sys
from magicbeans import common
from beancount.parser import parser
from beancount.core.data import Transaction
import dateutil.parser
import pytest

from magicbeans.transfers import Network, Link

def get_test_tx() -> Transaction:
    entries, errors, options = parser.parse_string("""
    2020-01-05 * "CBP: Buy 1.10 BTC"                       
      orderid: "47ac3b7d-f812-ac2bdff39-00fd1535bc8a"                    
      Assets:Coinbase:BTC           1.1 BTC {1000.00 USD}
      Assets:Coinbase:USD       -1105.0 USD               
      Expenses:Financial:Fees       5.0 USD               
    """)
    return entries[0]

def test_attach_timestamp_unaware() -> None:
    tx: Transaction = get_test_tx()
    naive_ts = "2020-01-05T16:12:51.376"
    timestamp = dateutil.parser.isoparse(naive_ts)
    with pytest.raises(Exception):
        common.attach_timestamp(tx, timestamp)

def test_attach_timestamp() -> None:
    tx: Transaction = get_test_tx()
    iso_ts = "2020-01-05T16:12:51.376Z"
    timestamp = dateutil.parser.isoparse(iso_ts)
    common.attach_timestamp(tx, timestamp)

    assert tx.meta["timestamp"] == iso_ts

