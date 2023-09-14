import datetime
from beancount.core.amount import Amount
from beancount.core.data import Posting, Transaction
from beancount.core.number import D
from magicbeans import disposals
from magicbeans.reports import driver
import pytest

def buy_tx(day: int):
    rcvd = Posting('Assets:Account:BTC', Amount(D('1.0'), 'BTC'), None, None, None, None)
    sent = Posting('Assets:Account:USD', Amount(D('-10000.0'), 'USD'), None, None, None, None)
    return Transaction({},
        datetime.date(2020, 1, 1) + datetime.timedelta(days=day),
        None, None, None, None, None,
        [rcvd, sent])

def sell_tx(day: int, n_lots: int):
    proceeds = Posting('Assets:Account:USD', Amount(D('10000.0'), 'USD'), None, None, None, None)
    lot_leg = Posting('Assets:Account:BTC', Amount(D('-1.0') / n_lots, 'BTC'), None, None, None, None)
    capgains_leg = Posting(disposals.STCG_ACCOUNT, Amount(D('0.0'), 'USD'), None, None, None, None)

    return Transaction({},
        datetime.date(2020, 1, 1) + datetime.timedelta(days=day),
        None, None, None, None, None,
        [proceeds] + [lot_leg] * n_lots + [capgains_leg])

def test_paginate__1():
    tx1 = buy_tx(day=0)
    tx2 = buy_tx(day=1)
    tx3 = buy_tx(day=2)
    tx4 = buy_tx(day=3)
    tx5 = buy_tx(day=4)

    all_entries = [ tx1, tx2, tx3, tx4, tx5 ]
    pages = list(driver.paginate_entries(all_entries, 3))

    # Each buy tx is 1 line, so tx4 and tx5 should go to page 2
    assert len(pages) == 2
    assert pages[0] == [ tx1, tx2, tx3 ]
    assert pages[1] == [ tx4, tx5 ]

def test_paginate__2():
    tx1 = buy_tx(day=0)
    tx2 = buy_tx(day=1)
    tx3 = buy_tx(day=1)
    tx4 = sell_tx(day=2, n_lots=2)

    all_entries = [ tx1, tx2, tx3, tx4 ]
    pages = list(driver.paginate_entries(all_entries, 5))

    # The first three buy tx's take three lines, and fit on the first page.
    # The sell tx needs another three lines, which doesn't fit in the page
    # size of 5.
    assert len(pages) == 2
    assert pages[0] == [ tx1, tx2, tx3 ]
    assert pages[1] == [ tx4 ]

def test_paginate__3():
    tx1 = sell_tx(day=0, n_lots=10)
    tx2 = buy_tx(day=1)

    all_entries = [ tx1, tx2 ]
    pages = list(driver.paginate_entries(all_entries, 5))

    # The first tx is a sell with many lots, so it should push the buy tx to
    # the next page.
    assert len(pages) == 2
    assert pages[0] == [ tx1 ]
    assert pages[1] == [ tx2 ]

