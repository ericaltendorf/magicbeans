from beancount.core import position

# Need to add a USD cost spec on transfers, see
#   https://github.com/beancount/beancount/issues/476
def usd_cost_spec():
    return position.CostSpec(None, None, "USD", None, None, None)
    # return position.Cost(None, "USD", None, None)
    # return None