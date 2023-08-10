"""Utilities for working with disposals"""

import datetime
from decimal import Decimal
import textwrap
from typing import List, NamedTuple
from beancount.core.data import Posting, Transaction

# TODO: get these account names from the config
STCG_ACCOUNT = "Income:CapGains:Short"
LTCG_ACCOUNT = "Income:CapGains:Long"

class DisposalSummary(NamedTuple):
    date: datetime.date
    narration: str
    short_term: Posting
    long_term: Posting
    gain_currency: str
    lots: List[Posting]

    def stcg(self) -> Decimal:
        if self.short_term:
            return - self.short_term.units.number
        else:
            return Decimal(0)

    def ltcg(self) -> Decimal:
        if self.long_term:
            return - self.long_term.units.number
        else:
            return Decimal(0)

def is_disposal_posting(posting: Posting):
	return (posting.account.startswith("Assets:")
	    and posting.units.number < 0
	    and posting.units.currency != "USD"
   		)

def render_disposal(disposal: Posting):
    return (
	    f"{disposal.units} "
		f"{{ {disposal.cost.number} {disposal.cost.currency}"
		f" {disposal.cost.date} }}"
		)

def abbrv_disposal(disposal: Posting):
	assert disposal.cost.currency == "USD"
	num = -disposal.units.number  # We render disposals as positive numbers
	if num.to_integral() == num:
		normalized_num = num.to_integral()
	else:
		normalized_num = num.normalize()
	return (
	    f"{normalized_num} "
		f"{{${disposal.cost.number:.4f} {disposal.cost.date}}}"
		)

def format_money(num: Decimal) -> str:
    if num:
        return f"{num:.2f}"
    else:
        return ""

def get_capgains_postings(entry: Transaction):
    """Return a pair of (short term, long term) capital gains postings as Decimal values"""
    # TODO: get these account names from the config
    st = [p for p in entry.postings if p.account == STCG_ACCOUNT]
    lt = [p for p in entry.postings if p.account == LTCG_ACCOUNT]
    if len(st) > 1 or len(lt) > 1 or (len(st) == 0 and len(lt) == 0):
        raise Exception(f"Expected one short term and/or one long term capital gains posting;"
                        f" got:   {st}  ,  {lt}")
    if st:
        assert st[0].units.currency == "USD"
    if lt:
        assert lt[0].units.currency == "USD"
    return (st[0] if st else None, lt[0] if lt else None)

def get_disposal_postings(entry: Transaction):
    return [p for p in entry.postings if is_disposal_posting(p)]

def render_lots(lots: List[Posting]):
	disposed_currencies = set([d.units.currency for d in lots])
	if len(disposed_currencies) > 1:
		raise Exception(f"Disposals should be of one currency; got: {disposed_currencies}")
	disposed_currency = disposed_currencies.pop()
	lots = sorted(lots, key=lambda d: d.units.number)  # Don't mutate args
	return f"{disposed_currency} " + ", ".join([abbrv_disposal(d) for d in lots])

def mk_disposal_summary(entry: Transaction):
    (st, lt) = get_capgains_postings(entry)
    disposal_postings = get_disposal_postings(entry)
    if st: assert st.units.currency == "USD"
    if lt: assert lt.units.currency == "USD" 
    return DisposalSummary(entry.date, entry.narration,
                           st, lt, "USD", disposal_postings)

# TODO: check logic.  check against red's plugin logic
def is_disposal_tx(entry: Transaction):
    return any((p.account in [STCG_ACCOUNT, LTCG_ACCOUNT] for p in entry.postings))


# TODO: should probably move to another file
def render_disposals_table(entries, file):
    file.write(f"{'Date':<12} {'Narration':<100} "
        f"{'STCG':>12} "
        f"{'Cumulative':>12} "
        f"{'LTCG':>12} "
        f"{'Cumulative':>12} "
        f"{'':>6}\n\n")

    cumulative_stcg = Decimal("0")
    cumulative_ltcg = Decimal("0")
    for e in entries:
        if isinstance(e, Transaction) and is_disposal_tx(e):
            summary = mk_disposal_summary(e)
   
            if summary.short_term:
                cumulative_stcg += summary.stcg()
            if summary.long_term:
                cumulative_ltcg += summary.ltcg()

			# TODO: hardcoded for ~140 char width now
            # TODO: why do i have to call str(summary.date)??
            file.write(f"{str(summary.date):<12} {summary.narration:<100} "
                f"{format_money(summary.stcg()):>12} "
                f"{cumulative_stcg:>12.2f} "
                f"{format_money(summary.ltcg()):>12} "
                f"{cumulative_ltcg:>12.2f} "
                f"{summary.gain_currency:>6}\n")
            file.write("\n".join(textwrap.wrap(
                f"Lots: {render_lots(summary.lots)}",
                width=112, initial_indent="  ", subsequent_indent="  ")))
            file.write("\n")

    file.write(f"\n{'':<12} {'Total for tax year {ty}':<100} "
        f"{'STCG':>12} "
        f"{cumulative_stcg:>12.2f} "
        f"{'LTCG':>12} "
        f"{cumulative_ltcg:>12.2f} "
        f"{'USD':>6}\n\n")   # TODO: hardcoded currency

