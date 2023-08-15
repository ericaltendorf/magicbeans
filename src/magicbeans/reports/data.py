"""Data structures for reporting"""

import datetime
from decimal import Decimal
from typing import List, NamedTuple, Tuple

from beancount.core.amount import Amount
from beancount.core.data import Posting
from beancount.core.position import Position

class AccountInventoryReport(NamedTuple):
    account: str
    total: Amount
    total_cost: Amount
    positions_and_ids: List[Tuple[Position, int]]

class InventoryReport(NamedTuple):
    date: datetime.date
    accounts: List[AccountInventoryReport]

class DisposalsReportRow(NamedTuple):
    date: datetime.date
    narration: str
    numeraire_proceeds: Decimal
    other_proceeds: Decimal
    disposed_cost: Decimal
    gain: Decimal
    stcg: Decimal
    cum_stcg: Decimal
    ltcg: Decimal
    cum_ltcg: Decimal
    disposed_currency: str
    numeraire_proceeds_legs: List[Posting]
    other_proceeds_legs: List[Posting]
    disposal_legs_and_ids: List[Tuple[Posting, int]]

class DisposalsReport(NamedTuple):
    start: datetime.date
    end: datetime.date
    numeraire: str
    rows: List[DisposalsReportRow]
    cumulative_stcg: Decimal
    cumulative_ltcg: Decimal
    extended: bool