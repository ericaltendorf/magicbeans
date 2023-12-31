"""Utilities for working with disposals"""

import datetime
from decimal import Decimal
from functools import partial
from typing import List, NamedTuple
from beancount.core import amount
from beancount.core.amount import Amount
from beancount.core.data import Posting, Transaction
from beancount.core.number import ZERO
from beancount.core.position import Cost, Position
from beancount.ops.summarize import balance_by_account

# TODO: get these account names from the config
ASSETS_ACCOUNT = "Assets"
CG_ACCOUNT = "Income:CapGains"
STCG_ACCOUNT = "Income:CapGains:Short"
LTCG_ACCOUNT = "Income:CapGains:Long"

class LotIndex():
	"""Tracks lots from inventories or acquisitions and enables ID assignment.

	This class enables us to create an index of lots (i.e., positions) from
	multiple accounts with an inventory snapshot, as well as from lots obtained
	in subsequent acquisition transactions, and index relevant ones from
	subsequent disposal transactions.
	"""

	# TODO: filter out numeraire accounts

	def __init__(self, inventory_blocks, acquisitions, disposals, numeraire):
		"""Initialize the index by adding lots from all inventories, and
		from the augmentation legs of all transactions.

		Args:
		- inventory_blocks: list of (currency, account, positions) tuples
		- acquisitions: acquisition transactions
		- disposals: disposal transactions
		- numeraire: needed to ignore cash-proceeds augmentations
		"""

		# Our index is logically a dict mapping
		#   (currency, Cost) to (ID number or None)
		# We share lots IDs across accounts in order to refer to a lot id even
		# if it's been transferred.
		self._index = {}

		referenced_lots = set()
		for e in disposals:
			for p in get_disposal_postings(e):
				referenced_lots.add(self._mk_key(p.units.currency, p.cost))

		# Use user-visible index IDs starting from 1, and in the order that lots
		# appear in inventory and acquisitions, so they're easy to find in the
		# report.
		self.next_id = 1

		available_lots = set()
		for (currency, account, positions) in inventory_blocks:
			for position in positions:
				key = self._mk_key(position.units.currency, position.cost)
				if key in referenced_lots:
					available_lots.add(key)
					self._assign_lotid(key[0], key[1])
		for tx in acquisitions:
			for posting in tx.postings:
				if is_other_proceeds_leg(posting, numeraire):
					key = self._mk_key(posting.units.currency, posting.cost)
					if key in referenced_lots:
						available_lots.add(key)
						self._assign_lotid(key[0], key[1])
		
		# for (currency, cost) in available_lots:
		# 	self._set(currency, cost, None)

		missing_lots = referenced_lots - available_lots
		for (currency, cost) in missing_lots:
			print(f"WARNING: missing lot for {currency} {{{cost.number} {cost.date}}}")


	# For robustness, round Cost values.  TODO: determine if this is necessary
	def _mk_key(self, currency, cost):
		num = cost.number.quantize(Decimal("1.0000")).normalize()
		return (currency, cost._replace(number=num))

	def _get(self, currency, cost):
		return self._index[self._mk_key(currency, cost)]

	def _has(self, currency, cost):
		return self._mk_key(currency, cost) in self._index

	def _set(self, currency, cost, new_value):
		self._index[self._mk_key(currency, cost)] = new_value

	def _assign_lotid(self, currency: str, cost: Cost) -> None:
		"""Finds the lot in the inventory, assigns an index number to it
		   if it doesn't already have one, remembers that and returns it"""
		self._set(currency, cost, self.next_id)
		self.next_id += 1

	def get_lotid(self, currency: str, cost: Cost) -> int:
		"""If this lot has been indexed, return the index, otherwise None"""
		if self._has(currency, cost):
			return self._get(currency, cost)
		return None

	def debug_str(self, currency=None) -> str:
		result = ""
		for (k, v) in self._index.items():
			lotid = v[1]
			if not lotid:
				continue
			if currency and k[1] != currency:
				continue
			result += f"  ({k[0]:<15} {k[1]:>6}, {k[2].number:>16f} {k[2].currency:<6} {k[2].date}: {lotid} )\n"
		return result

class BookedDisposal():
	"""Provides a view on a transaction which contains booked disposals
	
	The provided entry must be a transaction, it must have at least one
	reduction posting, and any reduction postings must already be fully
	booked (i.e., have an unambiguous cost assigned).
	
	One initialized, provides convenient accessors for explaining capital
	gains (in terms of the provided numeraire)."""

	def __init__(self, entry: Transaction, numeraire: str):
		if not isinstance(entry, Transaction):
			raise Exception(f"Expected a transaction, got: {entry}")
		if not is_disposal_tx(entry):
			raise Exception(f"Expected a disposal transaction, got: {entry}")
		self.tx = entry
		self.numeraire = numeraire
		self.numeraire_zero = Amount(ZERO, numeraire)

		# TODO: expect that this is a complete nonoverlapping partition?
		self.disposal_legs = self._filter_and_sort_legs(entry, is_disposal_leg)
		self.numeraire_proceeds_legs = self._filter_and_sort_legs(entry, is_numeraire_proceeds_leg)
		self.other_proceeds_legs = self._filter_and_sort_legs(entry, is_other_proceeds_leg)

		# Sanity check that all disposals are of the same currency, and hang on to it.
		disposed_currencies = set([d.units.currency for d in self.disposal_legs])
		if len(disposed_currencies) > 1:
			raise Exception(f"Disposals should be of one currency; got: {disposed_currencies}")
		self.disposed_currency = disposed_currencies.pop()

		# TODO: verify these add up to the gains we compute ourselves?
		(self.short_term, self.long_term) = get_capgains_postings(entry)

	def _filter_and_sort_legs(self, tx: Transaction, filter_pred):
		filter_pred_w_numeraire = partial(filter_pred, numeraire=self.numeraire)
		return sorted(filter(filter_pred_w_numeraire, tx.postings),
				key=lambda p: p.units.number)

	def acquisition_date(self) -> datetime.date:
		"""Return the date of the acquisition legs, if unique, otherwise "Various"."""
		dates = set([p.cost.date for p in self.disposal_legs])
		if len(dates) > 1:
			return "Various"
		return dates.pop()

	# TODO: this should just return self.disposed_currency, no?
	def disposed_asset(self) -> str:
		"""Return the name of the asset disposed"""
		all_disposed_assets = set([p.units.currency for p in self.disposal_legs])
		if len(all_disposed_assets) > 1:
			raise Exception(f"Expected one disposed asset, got: {all_disposed_assets}")
		return all_disposed_assets.pop()

	def disposed_amount(self) -> str:
		"""Return the total amount disposed"""
		amounts = [p.units.number for p in self.disposal_legs]
		return -sum(amounts)  # Return a positive number

	def total_numeriare_proceeds(self) -> Amount:
		"""Return the total proceeds obtained natively in the numeraire"""
		nums = [p.units for p in self.numeraire_proceeds_legs]
		return sum_amounts(self.numeraire, nums)

	def total_other_proceeds_value(self) -> Amount:
		"""Return the total value of the proceeds"""
		costs = [amount.mul(p.cost, p.units.number) for p in self.other_proceeds_legs]
		return sum_amounts(self.numeraire, costs)
	
	def total_disposed_cost(self) -> Amount:
		"""Return the total cost of the disposed assets"""
		costs = [amount.mul(p.cost, -p.units.number) for p in self.disposal_legs]
		return sum_amounts(self.numeraire, costs)

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

def is_disposal_leg(posting: Posting, numeraire: str) -> bool:
	return (posting.account.startswith(ASSETS_ACCOUNT)
		and posting.units.number < 0
		and posting.units.currency != numeraire
		)

def is_numeraire_proceeds_leg(posting: Posting, numeraire: str) -> bool:
	return (posting.account.startswith(ASSETS_ACCOUNT)
		and posting.units.number > 0
		and posting.units.currency == numeraire
		)

def is_other_proceeds_leg(posting: Posting, numeraire: str) -> bool:
	return (posting.account.startswith(ASSETS_ACCOUNT)
		and posting.units.number > 0
		and posting.units.currency != numeraire
		)

# TODO: Consolidate these functions
def disposal_inventory_desc(pos: Position, id: int) -> str:
	result = (f"{pos.units.number:.8f} {pos.units.currency} "
			  f"{{{pos.cost.number:0.4f} {pos.cost.date}}}")
	if id:
		result += f" (#{id})"
	return result

def disposal_inventory_ref(posting: Posting, id: int) -> str:
	result = (f"{posting.units.number:.4f} {posting.units.currency} {{"
	    	  + (f"#{id} " if id else "") +
			  f"{posting.cost.number:.4f} {posting.cost.currency}"
			  f" {posting.cost.date}}}")
	return result

def disposal_inventory_ref_neg(posting: Posting, id: int) -> str:
	result = (f"{-posting.units.number:.4f} {posting.units.currency} {{"
	    	  + (f"#{id} " if id else "") +
			  f"{posting.cost.number:.4f} {posting.cost.currency}"
			  f" {posting.cost.date}}}")
	return result

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

# TODO: remove, this should be obsoleted by BookedDisposal
class DisposalSummary(NamedTuple):
	date: datetime.date
	narration: str
	proceeds: Decimal
	short_term: Posting
	long_term: Posting
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

def is_proceeds_posting(posting: Posting):
	return (posting.account.startswith("Assets:")
		and posting.units.number > 0
		and posting.units.currency == "USD"
   		)

# TODO: remove, replaced by is_disposal_leg() above
def is_disposal_posting(posting: Posting):
	return (posting.account.startswith("Assets:")
		and posting.units.number < 0
		and posting.units.currency != "USD"
   		)

def sum_amounts(cur: str, amounts: List[Amount]) -> Amount:
	"""Add up a list of amounts, all of which must be in the same currency
	For some reason, sum() doesn't work for Amounts."""
	sum = Amount(ZERO, cur)
	for a in amounts:
		sum = amount.add(sum, a)
	return sum

# TODO: dedup this with the one in common
def format_money(num) -> str:
	if num:
		if isinstance(num, Amount) or isinstance(num, Cost):  # TODO: what a hack
			if num.currency == "USD":
				return f"${num.number:.2f}"
			else:
				return f"{num.number:.2f} {num.currency}"
		else:
			return f"{num:.2f}"
	else:
		return "--"

def get_capgains_postings(entry: Transaction):
	"""Return a pair of (short term, long term) capital gains postings as Decimal values"""
	# TODO: get these account names from the config
	cg = [p for p in entry.postings if p.account == CG_ACCOUNT]
	st = [p for p in entry.postings if p.account == STCG_ACCOUNT]
	lt = [p for p in entry.postings if p.account == LTCG_ACCOUNT]

	if len(cg) > 1:
		raise Exception(f"Expected at most one capital gains posting; got: {cg}")
	elif len(cg) == 1:
		# This should only happen when capital gains were zero, since the long_short plugin
		# will have moved all non-zero gains to the STCG and LTCG accounts.
		if any ((p.units.number != 0 for p in cg)):

			# TODO: fix this
			# raise Exception(f"Unexpected non-zero capital gains posting: {cg}")
			pass

		if len(st) > 0 or len(lt) > 0:
			raise Exception(f"Unexpected capital gains posting with STCG or LTCG postings: {cg}")
		assert cg[0].units.currency == "USD"
		return (cg[0], None)  # Arbitrary, since all are zero

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

def mk_disposal_summary(entry: Transaction):
	(st, lt) = get_capgains_postings(entry)
	disposal_postings = get_disposal_postings(entry)

	if st: assert st.units.currency == "USD"
	if lt: assert lt.units.currency == "USD" 

	total_proceeds = Decimal(0)
	for p in entry.postings:
		if is_proceeds_posting(p):
			assert p.units.currency == "USD"
			total_proceeds += p.units.number

	return DisposalSummary(entry.date, entry.narration, total_proceeds,
						   st, lt, disposal_postings)

# TODO: check logic.  check against red's plugin logic
def is_disposal_tx(entry: Transaction):
	# Note that if the cap gain were zero (as might happen if USDT is bought and spent on
	# the same day), the plugin leaves that in the generic CG_ACCOUNT.  We wish
	# to include those here for reporting even if no tax is due.
	all_cg_accounts = [CG_ACCOUNT, STCG_ACCOUNT, LTCG_ACCOUNT]
	return isinstance(entry, Transaction) and any((p.account in all_cg_accounts for p in entry.postings))
