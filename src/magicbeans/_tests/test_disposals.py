import datetime
from beancount.core.amount import Amount
from beancount.core.data import Posting, Transaction
from beancount.core.number import D
from beancount.core.position import Cost, Position
from magicbeans.disposals import LotIndex
import pytest

DAY1 = datetime.date(2015, 1, 1)
DAY2 = datetime.date(2016, 1, 1)
DAY3 = datetime.date(2021, 1, 1)

def usd_cost(amount: str, year: int):
    return Cost(D(amount), 'USD', datetime.date(year, 1, 1), None)

def nyd(year: int):
    return datetime.date(year, 1, 1)

def test_lotindex_from_inventories():
    account_to_inventory = {
        'Assets:MtGox': [
            Position(Amount(D('1.8'), 'BTC'), Cost(D('1000.0'), 'USD', nyd(2015), None)),
            Position(Amount(D('1.2'), 'BTC'), Cost(D('2000.0'), 'USD', nyd(2016), None)),
            ],
        'Assets:Coinbase': [
            Position(Amount(D('0.5'), 'BTC'), Cost(D('8000.0'), 'USD', nyd(2020), None)),
            ]
    }

    disposals = [
        Transaction({}, datetime.date(2022, 1, 1), None, None, None, None, None, [
            Posting('Assets:MtGox',
                    Amount(D('-0.2'), 'BTC'),
                    Cost(D('2000.0'), 'USD', nyd(2016), None),
                    None, None, None),
            Posting('Assets:Bank', Amount(D('6000'), 'USD'), None, None, None, None),
        ]),
        Transaction({}, datetime.date(2022, 1, 1), None, None, None, None, None, [
            Posting('Assets:Coinbase',
                    Amount(D('-0.2'), 'BTC'),
                    Cost(D('8000.0'), 'USD', nyd(2020), None),
                    None, None, None),
            Posting('Assets:Bank', Amount(D('6000'), 'USD'), None, None, None, None),
        ]),
    ]

    lotindex = LotIndex(account_to_inventory, [], disposals, "USD")

    # These should have been assigned IDs
    assert lotindex.get_lotid('BTC', usd_cost('2000.0', 2016)) == 2
    assert lotindex.get_lotid('BTC', usd_cost('8000.0', 2020)) == 1

    # This shouldn't have gotten an ID, but it should be in the index.
    assert ('BTC', usd_cost('1000.0', 2015)) in lotindex._index
    assert lotindex.get_lotid('BTC', usd_cost('1000.0', 2015)) == None