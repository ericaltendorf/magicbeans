from datetime import datetime
import re
from beancount.core import position
from beancount.core.data import Transaction

def attach_timestamp(entry: Transaction, ts: datetime):
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise Exception("Timestamps must be timezone aware")

    # This is so dumb.
    entry.meta['timestamp'] = re.sub(r'0*\+00:00', 'Z', ts.isoformat())
    None

# Need to add a USD cost spec on transfers, see
#   https://github.com/beancount/beancount/issues/476
def usd_cost_spec(transferred_currency):
    if transferred_currency == "USD":
        return None  # No cost basis needed to track
    
    return position.CostSpec(None, None, "USD", None, None, None)
    # return position.Cost(None, "USD", None, None)
    # return None