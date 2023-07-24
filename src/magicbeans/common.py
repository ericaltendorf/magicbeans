from datetime import datetime
import re
from beancount.core import position
from beancount.core.data import Transaction

def attach_timestamp(entry: Transaction, ts: datetime):
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise Exception("Timestamps must be timezone aware")

    # This is so dumb.
    fmt1 = ts.isoformat(timespec='milliseconds')
    fmt2 = fmt1.removesuffix('+00:00')
    fmt3 = fmt2.removesuffix('.000') + 'Z'
    entry.meta['timestamp'] = fmt3
    None

# Need to add a USD cost spec on transfers, see
#   https://github.com/beancount/beancount/issues/476
def usd_cost_spec(transferred_currency):
    if transferred_currency == "USD":
        return None  # No cost basis needed to track
    
    return position.CostSpec(None, None, "USD", None, None, None)
    # return position.Cost(None, "USD", None, None)
    # return None