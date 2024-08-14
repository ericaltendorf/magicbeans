import copy
import datetime
from decimal import Decimal
from typing import Callable, List, NamedTuple, Tuple
import typing
from beancount.core import position
from beancount.core.data import Posting, Transaction
import dateutil

class ExtractionRecord(NamedTuple):
    """A record of extractions from a particular file by an importer.
    
    This is a data structure Beangulp produces internally in its _extract()
    method, and which is passed to importer hooks.  We work with it because
    we imitate the importer process, and also the hooks mechanism because
    we allow users to define custom hooks to tweak their source data upon
    import.  Beangulp simply uses an untyped tuple, but we define it here with
    types so we can do typechecking.
    """
    filename: str
    entries: List[Transaction]
    account: str
    importer: str

def filter_extractions(
        extracted: typing.List[ExtractionRecord],
        filter_fn: Callable[[Transaction], bool]) -> typing.List[ExtractionRecord]:
    """Return a list of ExtractionRecords that omit transactions for which the
    provided predicate function returns True."""
    keep_fun = (lambda entry: not filter_fn(entry))
    return [ExtractionRecord(filename, list(filter(keep_fun, entries)), account, importer)
            for (filename, entries, account, importer) in extracted]

def file_begins_with(filepath: str, expected: str) -> bool:
    """Return True if the provided file begins with the provided string."""
    with open(filepath, "r") as file:
        head = file.read(len(expected))
        return head == expected

def rounded_amt(number: Decimal, currency: str, digits: int = None) -> position.Amount:
    """Return a position.Amount with the provided number and currency, rounded
       to the provided number of digits.  If digits is None, the number will be
       rounded to a default precision (or not rounded at all) based on the currency."""
    if digits is None:
        if currency == "USD":
            digits = 4
        elif currency == "USDT":
            digits = 8
        else:
            digits = 8   # TODO: this throws away precision; but it cleans up the reports
    if digits is not None:
        number = round(number, digits)
    return position.Amount(number, currency)

def format_money(num: Decimal, sym: str, dec_points: int, width: int) -> str:
    sym_width = len(sym)   # Only works if all rows use the same symbol
    if num:
        num_width = width - sym_width - 1
        return f"{num:>{num_width}.{dec_points}f} {sym:<{sym_width}}"
    else:
        return " " * width

def get_unique_posting_by_account(txn: Transaction, account: str) -> Posting:
    if not isinstance(txn, Transaction):
        raise Exception(f"Expected a Transaction, got {txn}")
    matched_postings = [p for p in txn.postings if p.account == account]
    if len(matched_postings) != 1:
        raise Exception(f"Expected exactly one posting with account {account} in {txn}")
    return matched_postings[0]

def maybe_get_unique_posting_by_account(txn: Transaction, account: str) -> Posting:
    if not isinstance(txn, Transaction):
        raise Exception(f"Expected a Transaction, got {txn}")
    matched_postings = [p for p in txn.postings if p.account == account]
    if len(matched_postings) == 1:
        return matched_postings[0]
    elif len(matched_postings) == 0:
        return None
    else:
        raise Exception(f"Expected no more than one posting with account {account} in {txn}")

def attach_timestamp(entry: Transaction, ts: datetime.datetime):
    """Attach a timestamp to the metadata of the provided transaction, formatted
    as a string in the standard ISO 8601 format using Z notation for UTC.  If a
    timestamp is already present, it will be overwritten."""
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise Exception("Timestamps must be timezone aware")

    # Python offers no reasonable way of producing "Z" notation.
    fmt1 = ts.isoformat(timespec='milliseconds')
    fmt2 = fmt1.removesuffix('+00:00')
    fmt3 = fmt2.removesuffix('.000') + 'Z'
    entry.meta['timestamp'] = fmt3
    None

def split_out_marked_fees(entry: Transaction, pnl_account) -> Tuple[Transaction, Transaction]:
    """Examine the provided transaction; if it contains fee postings,
    split those out into a separate transaction.  The provided tx will
    be modified to omit the fees while a new transaction containing
    the fees will be returned, with timestamp 1ms later."""
    reg_postings = []
    fee_postings = []
    for posting in entry.postings:
        meta = posting.meta
        if meta and 'is_fee' in meta and meta['is_fee']:
            fee_postings.append(posting)
        else:
            reg_postings.append(posting)
    
    if len(fee_postings) == 0:
        return (None, None)
    else:
        # Split fee and nonfee transactions, using a deep copy so we can mutate
        # the fee transaction without mutating the others.
        new_txn = copy.deepcopy(entry._replace(postings=reg_postings))
        fee_txn = copy.deepcopy(entry._replace(postings=fee_postings,
                                               narration="Fees for " + entry.narration))

        # Increment the timestamp so it comes after the original transaction.
        orig_ts = dateutil.parser.parse(fee_txn.meta['timestamp'])
        attach_timestamp(fee_txn, orig_ts + datetime.timedelta(milliseconds=1))

        return (new_txn, fee_txn)

# We used to need to add a USD cost spec on transfers, see
#   https://github.com/beancount/beancount/issues/476
# With our fix to cost bucketing (not yet checked into beancount head)
# that is no longer needed; we just use an empty cost spec for transfers.
# TODO: rename or remove this function.
def usd_cost_spec(transferred_currency):
    if transferred_currency == "USD":
        return None  # No cost basis needed to track
    
    return position.CostSpec(None, None, None, None, None, None)