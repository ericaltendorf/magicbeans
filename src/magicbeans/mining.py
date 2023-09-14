"""For mining, staking, farming, etc."""

from collections import defaultdict
from decimal import Decimal
from beancount.core.data import Transaction

# TODO: lots in common with disposals.render_disposals_table().  Refactor.

MINING_BENEFICIARY_ACCOUNT = "Assets:ChiaWallet:XCH"
MINING_INCOME_ACCOUNT = "Income:Mining:USD"

def is_mining_tx(entry):
    return (isinstance(entry, Transaction)
            and entry.narration
            and entry.narration.startswith("Mining reward"))

    # It feels cleaner to look for transactions with a posting to the mining
    # beneficiary account, but when FMV of mined coins is zero, beancount elides
    # that posting.  So we look for the narration instead.
    #
    # Example code of what we'd *like* to do:
    #
    # return (isinstance(entry, Transaction) and
    #     # TODO: should have both types of mining accounts
    #     any((p.account in [MINING_INCOME_ACCOUNT] for p in entry.postings)))
    # or
    #     has_entry_account_component()


class MiningStats:
    currency: str  # e.g. "XCH"
    n_events: int
    total_mined: Decimal
    total_fmv: Decimal   # in USD....

    def __init__(self, currency):
        self.currency = currency
        self.n_events = 0
        self.total_mined = Decimal(0)
        self.total_fmv = Decimal(0)

    def avg_award_size(self):
        if self.n_events == 0:
            return None
        else:
            return self.total_mined / self.n_events

    def avg_price(self):
        if self.total_mined == 0:
            return None
        else:
            return self.total_fmv / self.total_mined


