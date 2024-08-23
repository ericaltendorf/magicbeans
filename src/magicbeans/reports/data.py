"""Data structures for reporting"""

import datetime
from decimal import Decimal
from typing import List, NamedTuple, Tuple

# TODO: make these datastructures beancount-agnostic.
from beancount.core.amount import Amount
from beancount.core.data import Posting
from beancount.core.position import Position

class CoverPage(NamedTuple):
    title: str
    summary_lines: List[str]
    text: str

class TaxReportRow(NamedTuple):
    asset: str
    ltcg: Decimal
    stcg: Decimal
    ltcg_tax: Decimal
    stcg_tax: Decimal
    total_tax: Decimal

class TaxReport(NamedTuple):
    rows: List[TaxReportRow]
    total_row: TaxReportRow

class DisposalsSummaryRow(NamedTuple):
    disposed_currency: str
    disposed_amount: Decimal
    date: datetime.date
    acquisition_date: str  # May be "Various"
    numeraire_proceeds: Decimal
    other_proceeds: Decimal
    disposed_cost: Decimal
    gain: Decimal
    stcg: Decimal
    cum_stcg: Decimal
    ltcg: Decimal
    cum_ltcg: Decimal

class DisposalsSummaryTotalRow(NamedTuple):
    disposed_amount: Decimal
    numeraire_proceeds: Decimal
    other_proceeds: Decimal
    disposed_cost: Decimal
    gain: Decimal
    stcg: Decimal
    ltcg: Decimal

class DisposalsSummary(NamedTuple):
    title: str
    rows: List[DisposalsSummaryRow]
    total_row: DisposalsSummaryTotalRow

class AccountInventoryReport(NamedTuple):
    account: str
    total: Amount
    positions_and_ids: List[Tuple[Position, int]]

class InventoryReport(NamedTuple):
    ts: datetime.datetime
    accounts: List[AccountInventoryReport]

class AcquisitionsReportRow(NamedTuple):
    date: datetime.date
    narration: str
    amount: Decimal
    cur: str
    cost_ea: Decimal
    total_cost: Decimal
    lotid: int

# This used to be used for both the summary view of disposals (e.g. for 8949) as
# well as the detailed, lot-tracking transaction view.  Going forward this will
# be for just the transaction view.  TODO: consider a rename.
class DisposalsReportRow(NamedTuple):
    date: datetime.date
    acquisition_date: str  # May be "Various"
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
    disposed_amount: Decimal
    numeraire_proceeds_legs: List[Posting]
    other_proceeds_legs: List[Posting]
    disposal_legs_and_ids: List[Tuple[Posting, int]]
    num_legs_omitted: int

class DisposalsReport(NamedTuple):
    # start: datetime.date
    # end: datetime.date
    numeraire: str
    rows: List[DisposalsReportRow]
    cumulative_stcg: Decimal
    cumulative_ltcg: Decimal
    show_details: bool

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
