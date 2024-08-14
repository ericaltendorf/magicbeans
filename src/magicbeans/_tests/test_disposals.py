import datetime
from beancount.core.amount import Amount
from beancount.core.data import Posting, Transaction
from beancount.core.number import D
from beancount.core.position import Cost, Position
from magicbeans.disposals import InventoryBlock, LotIndex
import pytest

DAY1 = datetime.date(2015, 1, 1)
DAY2 = datetime.date(2016, 1, 1)
DAY3 = datetime.date(2021, 1, 1)

def usd_cost(amount: str, year: int):
    return Cost(D(amount), 'USD', datetime.date(year, 1, 1), None)

def nyd(year: int):
    return datetime.date(year, 1, 1)

def test_lotindex_from_inventories():
    inventory_blocks = [
        InventoryBlock('BTC', 'Assets:MtGox', [
            Position(Amount(D('1.8'), 'BTC'), usd_cost('1000.0', 2015)),
            Position(Amount(D('1.2'), 'BTC'), usd_cost('2000.0', 2016)), ]),
        InventoryBlock('BTC', 'Assets:Coinbase', [
            Position(Amount(D('0.5'), 'BTC'), usd_cost('8000.0', 2020)), ]),
    ]

    disposals = [
        Transaction({}, nyd(2022), None, None, None, None, None, [
            Posting('Assets:MtGox',
                    Amount(D('-0.2'), 'BTC'),
                    Cost(D('2000.0'), 'USD', nyd(2016), None),
                    None, None, None),
            Posting('Assets:Bank', Amount(D('6000'), 'USD'), None, None, None, None),
        ]),
        Transaction({}, nyd(2022), None, None, None, None, None, [
            Posting('Assets:Coinbase',
                    Amount(D('-0.2'), 'BTC'),
                    Cost(D('8000.0'), 'USD', nyd(2020), None),
                    None, None, None),
            Posting('Assets:Bank', Amount(D('6000'), 'USD'), None, None, None, None),
        ]),
    ]

    lotindex = LotIndex(inventory_blocks, [], disposals, "USD")

    # These should have been assigned IDs
    assert lotindex.get_lotid('BTC', usd_cost('2000.0', 2016)) == 1
    assert lotindex.get_lotid('BTC', usd_cost('8000.0', 2020)) == 2

def test_lotindex_from_acquisitions():
    acquisitions = [
        Transaction({}, nyd(2015), None, None, None, None, None, [
            Posting('Assets:MtGox',
                    Amount(D('1.8'), 'BTC'),
                    usd_cost('1000.0', 2015),
                    None, None, None),
            Posting('Assets:Bank', Amount(D('-1800'), 'USD'), None, None, None, None),
        ]),
        Transaction({}, nyd(2016), None, None, None, None, None, [
            Posting('Assets:MtGox',
                    Amount(D('0.2'), 'BTC'),
                    # TODO: is this realistic the cost is here?  it's not inferred from the other leg?
                    usd_cost('2000.0', 2016),
                    None, None, None),
            Posting('Assets:Bank', Amount(D('-6000'), 'USD'), None, None, None, None),
        ]),
    ]

    disposals = [
        Transaction({}, nyd(2022), None, None, None, None, None, [
            Posting('Assets:MtGox',
                    Amount(D('-0.1'), 'BTC'),
                    usd_cost('2000.0', 2016),
                    None, None, None),
            Posting('Assets:Bank', Amount(D('6000'), 'USD'), None, None, None, None),
        ]),
    ]

    lotindex = LotIndex([], acquisitions, disposals, "USD")

    print(lotindex.debug_str())

    # This should have been assigned an ID
    assert lotindex.get_lotid('BTC', usd_cost('2000.0', 2016)) == 2
 


