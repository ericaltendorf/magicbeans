import copy
import datetime
import re
from typing import Tuple
from beancount.core import position
from beancount.core import data
from beancount.core.data import Posting, Transaction
import dateutil

def attach_timestamp(entry: Transaction, ts: datetime.datetime):
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise Exception("Timestamps must be timezone aware")

    # This is so dumb.
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
        orig_tx = dateutil.parser.parse(fee_txn.meta['timestamp'])
        attach_timestamp(fee_txn, orig_tx + datetime.timedelta(milliseconds=1))

        return (new_txn, fee_txn)

# Need to add a USD cost spec on transfers, see
#   https://github.com/beancount/beancount/issues/476
def usd_cost_spec(transferred_currency):
    if transferred_currency == "USD":
        return None  # No cost basis needed to track
    
    return position.CostSpec(None, None, "USD", None, None, None)
    # return position.Cost(None, "USD", None, None)
    # return None