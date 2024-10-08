"""Utilities for working with disposals"""

import datetime
from decimal import Decimal
from functools import partial
from typing import Dict, List, NamedTuple, Sequence, Tuple

import dateutil
from beancount.parser.printer import format_entry
from beancount.parser.printer import print_entry
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

def assert_valid_position(position):
	assert(position.cost is not None), f"Position {position} has no cost"

class InventoryBlock(NamedTuple):
	currency: str
	account: str
	positions: List[Position]

class LotIndex():
	"""Tracks lots from inventories or acquisitions and enables ID assignment.

	This class enables us to create an index of lots (i.e., positions) from
	multiple accounts with an inventory snapshot, as well as from lots obtained
	in subsequent acquisition transactions, and index relevant ones from
	subsequent disposal transactions.
	"""

	# TODO: filter out numeraire accounts

	def __init__(self, inventory_blocks: Sequence[InventoryBlock], acquisitions:
	Sequence[Transaction], disposals: Sequence[Transaction], numeraire: str):
		"""Initialize the index for a set of inventories and transactions.
		
		This will collect lots from inventories and the augmentation legs
		of transactions, identify the relevant ones based on the disposals,
		and index those for future reference.

		Args:
		- inventory_blocks: list of (currency, account, positions) tuples
		- acquisitions: acquisition transactions (purchases and mining awards)
		- disposals: disposal transactions
		- numeraire: needed to ignore cash-proceeds augmentations
		"""

		# Our index is logically a dict mapping
		#   (currency, Cost) to (ID number or None)
		# where currency is the held asset.
		#
		# We share lots IDs across accounts in order to refer to a lot id even
		# if it's been transferred.
		self._index: Dict[Tuple[str, Cost], int] = {}

		# Collect all lots that are referenced in disposals
		referenced_lots = set()
		for e in disposals:
			for a in get_disposal_postings(e, numeraire):
				key = self._mk_key(a.units.currency, a.cost)
				referenced_lots.add(key)


		# Use user-visible index IDs starting from 1, and in the order that lots
		# appear in inventory and acquisitions, so they're easy to find in the
		# report.
		self.next_id = 1

		# Index all lots from inventories and acquisitions
		indexed_lots = set()
		for (currency, account, positions) in inventory_blocks:
			for position in positions:
				assert_valid_position(position)
				key = self._mk_key(position.units.currency, position.cost)
				if key in referenced_lots:
					indexed_lots.add(key)
					self._assign_lotid(key[0], key[1])
		for tx in list(acquisitions) + list(disposals):
			for posting in tx.postings:
				if is_non_numeraire_proceeds_leg(posting, numeraire):
					key = self._mk_key(posting.units.currency, posting.cost)
					if key in referenced_lots:
						indexed_lots.add(key)
						self._assign_lotid(key[0], key[1])
		
		# for (currency, cost) in available_lots:
		# 	self._set(currency, cost, None)

		missing_lots = referenced_lots - indexed_lots
		if missing_lots:
			print("\n!!! Warning: LotIndex had no index for these referenced lots:")
			for (currency, cost) in missing_lots:
				print(f"!!!   {currency} {{{cost.number} {cost.currency} {cost.date}}}")
			all_tx = list(acquisitions) + list(disposals)
			tx_earliest = min([tx.date for tx in all_tx], default=None)
			tx_latest = max([tx.date for tx in all_tx], default=None)
			print(f'!!! Indexed lots (inc. tx between {tx_earliest} and {tx_latest}:')
			for line in self.debug_str():
				print(f"!!!   {line}")


	# For robustness, round Cost values.  TODO: determine if this is necessary
	def _mk_key(self, currency: str, cost: Cost):
		num = cost.number.quantize(Decimal("1.00000000")).normalize()
		return (currency, cost._replace(number=num))

	def _get(self, currency: str, cost: Cost):
		return self._index[self._mk_key(currency, cost)]

	def _has(self, currency: str, cost: Cost):
		return self._mk_key(currency, cost) in self._index

	def _set(self, currency: str, cost: Cost, new_value):
		self._index[self._mk_key(currency, cost)] = new_value

	def _assign_lotid(self, currency: str, cost: Cost) -> None:
		"""Finds the lot in the inventory, assigns an index number to it
		   if it doesn't already have one, remembers that and returns it"""
		self._set(currency, cost, self.next_id)
		self.next_id += 1

	def get_lotid(self, currency: str, cost: Cost) -> int | None:
		"""If this lot has been indexed, return the index, otherwise None"""
		if self._has(currency, cost):
			return self._get(currency, cost)
		return None

	def render_lot(self, currency: str, cost: Cost) -> str:
		"""Return a string representation of the lot"""
		return f"{currency:<15} {cost.number:>16f} {cost.currency:<6} {cost.date}"

	def debug_str(self, select_currency=None) -> List[str]:
		result = []
		for ((currency, cost), lotid) in self._index.items():
			if not lotid:
				continue
			if select_currency and currency != select_currency:
				continue
			result.append(f"  {self.render_lot(currency, cost)} -> #{lotid}")
		return result

class BookedDisposal():
	"""Provides a view on a transaction which contains booked disposals
	
	The provided entry must be a transaction, it must have at least one
	reduction posting, and any reduction postings must already be fully
	booked (i.e., have an unambiguous cost assigned).
	
	One initialized, provides convenient accessors for explaining capital
	gains (in terms of the provided numeraire)."""

	disposal_legs: Sequence[Posting]
	numeraire_proceeds_legs: Sequence[Posting]
	other_proceeds_legs: Sequence[Posting]

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
		self.other_proceeds_legs = self._filter_and_sort_legs(entry, is_non_numeraire_proceeds_leg)

		# Sanity check that all disposals are of the same currency, and hang on to it.
		disposed_currencies = set([d.units.currency for d in self.disposal_legs])
		if len(disposed_currencies) > 1:
			raise Exception(f"Disposals should be of one currency; got: {disposed_currencies}")
		self.disposed_currency = disposed_currencies.pop()

		# TODO: verify these add up to the gains we compute ourselves?
		(self.short_term, self.long_term) = get_capgains_postings(entry)

	def _filter_and_sort_legs(self, tx: Transaction, filter_pred) -> Posting:
		filter_pred_w_numeraire = partial(filter_pred, numeraire=self.numeraire)
		return sorted(filter(filter_pred_w_numeraire, tx.postings),
				key=lambda p: p.units.number)

	def timestamp(self) -> datetime.datetime:
		"""Return the timestamp of the transaction"""
		return dateutil.parser.parse(self.tx.meta["timestamp"])

	def acquisition_date(self) -> str:
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

	def disposed_amount(self) -> Decimal:
		"""Return the total amount disposed"""
		amounts = [p.units.number for p in self.disposal_legs]
		return -sum(amounts)  # Return a positive number

	def disposal_date(self) -> datetime.date:
		"""Return the date of the disposal"""
		return self.tx.date

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

class BDGroupKey(NamedTuple):
	asset: str
	acquired: str  # May be "Various"
	disposed: datetime.date

	@staticmethod
	def new(bd: BookedDisposal):
		return BDGroupKey(bd.disposed_asset(), bd.acquisition_date(), bd.timestamp().date())

class BookedDisposalGroup():
	"""Looks like a BookedDisposal for reporting, but actually a group of them.
	TODO: explicitly define the shared interface."""
	def __init__(self, bd: BookedDisposal):
		self.numeraire = bd.numeraire
		self.idx = BDGroupKey.new(bd)
		self.disposals = [bd]

	def add(self, bd: BookedDisposal):
		if self.idx != BDGroupKey.new(bd):
			raise Exception(f"Cannot add {bd} (key {BDGroupKey.new(bd)} to {self} (key {self.idx})")
		if self.numeraire != bd.numeraire:
			raise Exception(f"Cannot add {bd} (numeraire {bd.numeraire} to {self} (numeraire {self.numeraire})")
		self.disposals.append(bd)

	def zero(self) -> Amount:
		return Amount(ZERO, self.disposals[0].numeraire)

	def acquisition_date(self) -> str:
		return self.idx.acquired
	
	def disposed_asset(self) -> str:
		return self.idx.asset

	def disposed_amount(self) -> Decimal:
		return sum([bd.disposed_amount() for bd in self.disposals], Decimal(0))

	def disposal_date(self) -> datetime.date:
		return self.idx.disposed
	
	def total_numeriare_proceeds(self) -> Amount:
		return sum_amounts(self.numeraire, [bd.total_numeriare_proceeds() for bd in self.disposals])
	
	def total_other_proceeds_value(self) -> Amount:
		return sum_amounts(self.numeraire, [bd.total_other_proceeds_value() for bd in self.disposals])
	
	def total_disposed_cost(self) -> Amount:
		return sum_amounts(self.numeraire, [bd.total_disposed_cost() for bd in self.disposals])
	
	def stcg(self) -> Decimal:
		return sum(([bd.stcg() for bd in self.disposals]), Decimal(0))
	
	def ltcg(self) -> Decimal:
		result = sum(([bd.ltcg() for bd in self.disposals]), Decimal(0))
		return result


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

def is_non_numeraire_proceeds_leg(posting: Posting, numeraire: str) -> bool:
	return (posting.account.startswith(ASSETS_ACCOUNT)
		and posting.units.number > 0
		and posting.units.currency != numeraire
		)

def disposal_inventory_ref_neg(posting: Posting, id: int) -> str:
	result = (f"{-posting.units.number:.4f} {posting.units.currency} {{"
	    	  + (f"#{id} " if id else "") +
			  f"{posting.cost.number:.4f} {posting.cost.currency}"
			  f" {posting.cost.date}}}")
	return result

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

def get_disposal_postings(entry: Transaction, numeraire: str):
	return [p for p in entry.postings if is_disposal_leg(p, numeraire)]

# TODO: check logic.  check against red's plugin logic
def is_disposal_tx(entry: Transaction):
	# Note that if the cap gain were zero (as might happen if USDT is bought and spent on
	# the same day), the plugin leaves that in the generic CG_ACCOUNT.  We wish
	# to include those here for reporting even if no tax is due.
	all_cg_accounts = [CG_ACCOUNT, STCG_ACCOUNT, LTCG_ACCOUNT]
	return isinstance(entry, Transaction) and any((p.account in all_cg_accounts for p in entry.postings))
