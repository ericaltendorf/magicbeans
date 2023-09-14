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
        None, None, f"tx{day}", None, None,
        [rcvd, sent])

def sell_tx(day: int, n_lots: int):
    proceeds = Posting('Assets:Account:USD', Amount(D('10000.0'), 'USD'), None, None, None, None)
    lot_leg = Posting('Assets:Account:BTC', Amount(D('-1.0') / n_lots, 'BTC'), None, None, None, None)
    capgains_leg = Posting(disposals.STCG_ACCOUNT, Amount(D('0.0'), 'USD'), None, None, None, None)

    return Transaction({},
        datetime.date(2020, 1, 1) + datetime.timedelta(days=day),
        None, None, f"tx{day}", None, None,
        [proceeds] + [lot_leg] * n_lots + [capgains_leg])

def assert_pgs_equal(actual, expected):
    def to_narrations(page):
        return [[tx.narration for tx in txs] for txs in page]
    assert to_narrations(actual) == to_narrations(expected)

def test_paginate__1():
    tx1 = buy_tx(day=0)  # Line 1, page 1
    tx2 = buy_tx(day=1)  # Line 2, page 1
    tx3 = buy_tx(day=2)  # Line 3, page 1
    tx4 = buy_tx(day=3)  # Line 1, page 2
    tx5 = buy_tx(day=4)  # Line 2, page 2

    all_entries = [ tx1, tx2, tx3, tx4, tx5 ]
    pages = list(driver.paginate_entries(all_entries, 3))

    assert_pgs_equal(pages, [ [ tx1, tx2, tx3 ], [ tx4, tx5 ] ])

def test_paginate__2():
    tx1 = buy_tx(day=0)             # Line 1, page 1
    tx2 = buy_tx(day=1)             # Line 2, page 1
    tx3 = buy_tx(day=2)             # Line 3, page 1
    tx4 = sell_tx(day=3, n_lots=2)  # Lines 1-3, page 2

    all_entries = [ tx1, tx2, tx3, tx4 ]
    pages = list(driver.paginate_entries(all_entries, 5))

    assert_pgs_equal(pages, [ [ tx1, tx2, tx3 ], [ tx4 ] ])

def test_paginate__3():
    tx1 = sell_tx(day=0, n_lots=10)  # Lines 1-11, page 1
    tx2 = buy_tx(day=1)              # Line 1, page 2

    all_entries = [ tx1, tx2 ]
    pages = list(driver.paginate_entries(all_entries, 5))

    assert_pgs_equal(pages, [ [ tx1 ], [ tx2 ] ])

def test_paginate__4():
    tx1 = sell_tx(day=0, n_lots=4)  # Lines 1-5, page 1
    tx2 = buy_tx(day=1)             # Line 1, page 2
    tx3 = buy_tx(day=2)             # Line 2, page 2

    all_entries = [ tx1, tx2, tx3 ]
    pages = list(driver.paginate_entries(all_entries, 5))

    assert_pgs_equal(pages, [ [ tx1 ], [ tx2, tx3 ] ])