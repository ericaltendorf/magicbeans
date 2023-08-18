"""Data structures for reporting"""

import datetime
from decimal import Decimal
from typing import List, NamedTuple, Tuple

from beancount.core.amount import Amount
from beancount.core.data import Posting
from beancount.core.position import Position

class CoverPage(NamedTuple):
    title: str
    summary_lines: List[str]
    text: str

class AccountInventoryReport(NamedTuple):
    account: str
    total: Amount
    positions_and_ids: List[Tuple[Position, int]]

class InventoryReport(NamedTuple):
    date: datetime.date
    accounts: List[AccountInventoryReport]

class AcquisitionsReportRow(NamedTuple):
    date: datetime.date
    narration: str
    amount: Decimal
    cur: str
    cost_ea: Decimal
    total_cost: Decimal
    lotid: int

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

class MiningSummaryRow(NamedTuple):
    currency: str
    month: int
    n_awards: int
    amount_mined: Decimal
    avg_award_size: Decimal
    cumul_total: Decimal
    avg_cost: Decimal
    fmv_earned: Decimal
    cumulative_fmv: Decimal
