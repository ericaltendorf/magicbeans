"""For mining, staking, farming, etc."""

import calendar
from collections import defaultdict
from decimal import Decimal
from beancount.core.data import Transaction
from magicbeans import common

# TODO: lots in common with disposals.render_disposals_table().  Refactor.

MINING_BENEFICIARY_ACCOUNT = "Assets:ChiaWallet:XCH"
MINING_INCOME_ACCOUNT = "Income:Mining:USD"

def is_mining_tx(entry):
    return (isinstance(entry, Transaction)
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


def render_mining_summary(entries, file):
    currency = "XCH"
    mining_stats_by_month = [MiningStats(currency) for _ in range(12)]
    
    for e in entries:
        if is_mining_tx(e):
            income_posting = common.maybe_get_unique_posting_by_account(
                e, MINING_INCOME_ACCOUNT)
            if income_posting and income_posting.units.currency != "USD":
                raise ValueError(f"Unexpected currency: {income_posting.units.currency}")
            
            beneficiary_posting = common.get_unique_posting_by_account(
                e, MINING_BENEFICIARY_ACCOUNT)
            if beneficiary_posting.units.currency != "XCH":
                raise ValueError(f"Unexpected currency: {beneficiary_posting.units.currency}")

            month = e.date.month - 1
            stats = mining_stats_by_month[month]

            stats.n_events += 1
            stats.total_mined += Decimal(beneficiary_posting.units.number)
            if income_posting:
                stats.total_fmv -= Decimal(income_posting.units.number)


    if not any(stats.n_events for stats in mining_stats_by_month):
        file.write("\n(No mining income)\n")
        return

    # TODO: this one might actually be better rendered by beanquery query rendering....

    file.write("\n"
        f"{'Month':<6}"
        f"{'#Awards':>8}"
        f"{'Amount mined':>24}"
        f"{'Avg award size':>20}"
        f"{'Cumulative total':>24}"
        f"{'Avg. cost':>20}"
        f"{'FMV earned':>20}"
        f"{'Cumulative FMV':>20}\n\n")

    cumulative_mined = Decimal(0)
    cumulative_fmv = Decimal(0)
    token = "XCH"
    tok_price_units = f"USD/{token}"
    for (month, stats) in enumerate(mining_stats_by_month):
        cumulative_mined += stats.total_mined
        cumulative_fmv += stats.total_fmv
        file.write(
            f"{calendar.month_abbr[month + 1]:<6}"
            f"{stats.n_events:>8}"
            f"{common.format_money(stats.total_mined, token, 8, 24)}"
            f"{common.format_money(stats.avg_award_size(), token, 8, 20)}"
            f"{common.format_money(cumulative_mined, token, 4, 24)}"
            f"{common.format_money(stats.avg_price(), tok_price_units, 4, 20)}"
            f"{common.format_money(stats.total_fmv, 'USD', 4, 20)}"
            f"{common.format_money(cumulative_fmv, 'USD', 2, 20)}"
             "\n")

    file.write(f"\n{'':6}{'':8}"
               f"{'Total cumulative fair market value of all mined tokens:':>{24 + 20 + 24 + 20 + 20}}"
               f"{common.format_money(cumulative_fmv, 'USD', 2, 20)}")
