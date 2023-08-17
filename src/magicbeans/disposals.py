"""Utilities for working with disposals"""

import datetime
from decimal import Decimal
from typing import List, NamedTuple
from beancount.core import amount
from beancount.core.amount import Amount
from beancount.core.data import Posting, Transaction
from beancount.core.number import ZERO
from beancount.core.position import Cost, Position
from beancount.ops.summarize import balance_by_account

# TODO: get these account names from the config
ASSETS_ACCOUNT = "Assets"
STCG_ACCOUNT = "Income:CapGains:Short"
LTCG_ACCOUNT = "Income:CapGains:Long"

class ReductionIndexedInventory():
	"""A wrapper around beancount Inventory objects for reporting disposals.

	This class aggregates inventories of multiple accounts and also provides
	a way to assign user-reportable index numbers to lots in the inventory(s) in
	order to generate reports which associate reductions in disposal transactions
	back to lots in an inventory list."""

	# TODO: filter out numeraire accounts

	def __init__(self, account_to_inventory):
		"""account_to_inventory is a dict mapping account names to inventories,
		as returned by beancount.ops.summarize.balance_by_account()"""

		# Our index is a dict mapping
		#   (account name, Cost) to (Position, ID number or None)
		self.index = {}

		self.account_to_inventory = account_to_inventory

		self.accounts = set()
		for (account, inventory) in self.account_to_inventory.items():
			for pos in inventory:
				self.index[(account, pos.cost)] = (pos, None)
			self.accounts.add(account)
			
		self.next_id = 1

	def index_lot(self, account: str, cost: Cost):
		"""Finds the lot in the inventory, assigns an index number to it
		   if it doesn't already have one, remembers that and returns it"""
		if not (account, cost) in self.index:
			# print(f"warning: Lot not found in inventory: {account} {cost}")
			pass
			
		(position, id) = self.index[(account, cost)]
		if id is None:
			self.index[(account, cost)] = (position, self.next_id)
			self.next_id += 1

		return self.index[(account, cost)][1]

	def index_contains(self, account: str, cost: Cost):
		"""Return True if this lot has been indexed"""
		return (account, cost) in self.index

	def lookup_lot_id(self, account: str, cost: Cost):
		"""If this lot has been indexed, return the index, otherwise None"""
		if not (account, cost) in self.index:
			# print(f"Lot not found in inventory: {account} {cost}")
			return None
			# raise Exception(f"Lot not found in inventory: {account} {cost} "
			#                 f"Available: {self.index.keys()}")
		return self.index[(account, cost)][1]

	def get_accounts(self):
		return self.accounts
	
	# TODO: if we move this out of this class, then this class doesn't
	# need to remember account_to_inventory, which might simplify things.
	def get_inventory_w_ids(self, account: str):
		"""For a given account, return a list of (position, id) pairs."""
		return [(pos, self.lookup_lot_id(account, pos.cost))
				for pos in self.account_to_inventory[account]]


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
		self.disposal_legs = self._filter_and_sort_legs(entry, self.is_disposal_leg)
		self.numeraire_proceeds_legs = self._filter_and_sort_legs(entry, self.is_numeraire_proceeds_leg)
		self.other_proceeds_legs = self._filter_and_sort_legs(entry, self.is_other_proceeds_leg)

		# Sanity check that all disposals are of the same currency, and hang on to it.
		disposed_currencies = set([d.units.currency for d in self.disposal_legs])
		if len(disposed_currencies) > 1:
			raise Exception(f"Disposals should be of one currency; got: {disposed_currencies}")
		self.disposed_currency = disposed_currencies.pop()

		# TODO: verify these add up to the gains we compute ourselves?
		(self.short_term, self.long_term) = get_capgains_postings(entry)

	@staticmethod
	def _filter_and_sort_legs(tx: Transaction, predicate):
		return sorted(filter(predicate, tx.postings),
				key=lambda p: p.units.number)

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

	def is_disposal_leg(self, posting: Posting) -> bool:
		return (posting.account.startswith(ASSETS_ACCOUNT)
			and posting.units.number < 0
			and posting.units.currency != self.numeraire
			)

	def is_numeraire_proceeds_leg(self, posting: Posting) -> bool:
		return (posting.account.startswith(ASSETS_ACCOUNT)
			and posting.units.number > 0
			and posting.units.currency == self.numeraire
			)

	def is_other_proceeds_leg(self, posting: Posting) -> bool:
		return (posting.account.startswith(ASSETS_ACCOUNT)
			and posting.units.number > 0
			and posting.units.currency != self.numeraire
			)

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
	return isinstance(entry, Transaction) and any((p.account in [STCG_ACCOUNT, LTCG_ACCOUNT] for p in entry.postings))
