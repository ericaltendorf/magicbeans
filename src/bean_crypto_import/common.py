from beancount.core import position

# Need to add a USD cost spec on transfers, see
#   https://github.com/beancount/beancount/issues/476
def usd_cost_spec(transferred_currency):
    if transferred_currency == "USD":
        return None  # No cost basis needed to track
    
    return position.CostSpec(None, None, "USD", None, None, None)
    # return position.Cost(None, "USD", None, None)
    # return None