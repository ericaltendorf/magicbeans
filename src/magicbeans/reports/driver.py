import calendar
import datetime
from decimal import Decimal
import subprocess
import sys
from enum import Enum
import textwrap
from typing import List
from beancount.core import amount
from beancount.core.data import Transaction
from beancount.core.number import ZERO
from beancount.ops import summarize
from magicbeans import common
from magicbeans import disposals
from magicbeans.disposals import check_and_sort_lots, format_money, get_disposal_postings, is_disposal_tx, mk_disposal_summary, sum_amounts
from magicbeans.mining import MINING_BENEFICIARY_ACCOUNT, MINING_INCOME_ACCOUNT, MiningStats, is_mining_tx
from magicbeans.reports.text import TextRenderer

from pyfiglet import Figlet
from tabulate import tabulate

from beancount import loader
from beancount.core.amount import Amount
from beancount.parser import parser
from beanquery.query import run_query
from beanquery.query_render import render_text


def beancount_quarter(ty: int, quarter_n: int):
	return f"{ty}-Q{quarter_n}"


class ReportDriver:
	"""Wraps a beancount file and facilitates reporting with BQL queries.

	Initialize the driver with the path to the beancount file and the path to
	the output report file.  Then call the other methods to run queries and
	write the results to the report file.
	"""	

	# TODO: query(), render(), and query_and_render() may be obsolete now.

	def __init__(self, ledger_path: str, out_path: str) -> None:
		"""Load the beancount file at the given path and parse it for queries, 
		and initialize the output report file."""
		self.report = open(out_path, 'w')   # TODO: verify this is closed on destruction
		self.renderer = TextRenderer(self.report)

		entries, _errors, options = loader.load_file(ledger_path)
		self.entries = entries
		self.options = options
	
	# TODO: remove
	def w(self, s: str):
		self.report.write(s)
	
	#
	# Old report methods, mostly for bean-query driven reports
	#
	
	def query(self, query: str):
		"""Run a bean-query query on the entries in this database.  Returns a
		list of (name, dtype) tuples describing the results set table and a list
		of ResultRow tuples with the data.item pairs."""
		return run_query(self.entries, self.options, query)

	def query_and_render(self, query: str, footer: str = None):
		(rtypes, rrows) = self.query(query)
		self.renderer.beanquery_table(rtypes, rrows, footer)

	def run_subreport(self, title: str, query: str, footer: str = None):
		self.renderer.subreport_header(title, query)
		self.query_and_render(query, footer)

	#
	# New report methods, using direct analysis of the entries
	#

	def run_disposals_subreport(self, title: str, ty: int):
		self.renderer.subreport_header(title)

		# see this: 
		# def iter_entry_dates(entries, date_begin, date_end):
		ty_entries = [e for e in self.entries if e.date.year == ty]

		cumulative_stcg = Decimal("0")
		cumulative_ltcg = Decimal("0")
		cumulative_proceeds = Decimal("0")

		num_lines = 0

		self.renderer.start_disposals_table()
		for e in ty_entries:
			if isinstance(e, Transaction) and is_disposal_tx(e):
				num_lines += 1
				summary = mk_disposal_summary(e)

				if summary.short_term:
					cumulative_stcg += summary.stcg()
				if summary.long_term:
					cumulative_ltcg += summary.ltcg()
				if summary.proceeds:
					cumulative_proceeds += summary.proceeds

				(disposed_currency, lots) = check_and_sort_lots(summary.lots)
				self.renderer.disposal_row(
					summary.date, summary.narration, summary.proceeds,
					None, # TODO
					None, None,# TODO
					summary.stcg(), cumulative_stcg,
					summary.ltcg(), cumulative_ltcg,
					disposed_currency, lots)

		if num_lines == 0:
			self.renderer.write_text("(No disposals)\n")

		self.renderer.end_disposals_table(
			cumulative_proceeds,
			Decimal("0.00"),  # TODO
			Decimal("0.00"),  # TODO
			Decimal("0.00"),  # TODO
			cumulative_stcg, cumulative_ltcg)

	def run_disposals_details(self, start: datetime, end: datetime):
		numeraire = "USD"

		(account_to_inventory, index) = summarize.balance_by_account(
			self.entries, start)

		# Remove numeraire-only accounts; we don't need to track those
		for (account, inventory) in list(account_to_inventory.items()):
			if all([p.units.currency == numeraire for p in inventory]):
				account_to_inventory.pop(account)

		# Define the inventory and get it set up for indexing
		inventory_idx = disposals.ReductionIndexedInventory(account_to_inventory)

		# Define the list of transactions to process on this page
		page_entries = summarize.truncate(self.entries[index:], end)
		page_entries = list(filter(is_disposal_tx, page_entries))

		# Index reduced lots with IDs
		for e in page_entries:
			for p in get_disposal_postings(e):
				account = p.account
				if inventory_idx.index_contains(account, p.cost):
					lot_id = inventory_idx.index_lot(account, p.cost)
				else:
					# TODO: this disposal may be of something acquired after
					# the inventory-index was created.
					#print(f"Warning: cost {p.cost} not found in inventory")
					pass

		# Write ante-inventory with IDs
		self.renderer.start_inventory_table(start)
		for account in inventory_idx.get_accounts():
			cur_to_inventory = account_to_inventory[account].split()
			for (cur, inventory) in cur_to_inventory.items():
				items = inventory_idx.get_inventory_w_ids(account)
				total = sum_amounts(cur, [pos.units for (pos, id) in items])
				self.renderer.start_inventory_account(account, cur, total)

				sorted_pairs = sorted(items, key=lambda x: -abs(x[0].units.number))
				for (pos, lot_id) in sorted_pairs:
					self.renderer.inventory_row(pos, lot_id)
		self.renderer.end_inventory_table()

		# Write disposal transactions referencing IDs
		self.renderer.start_disposals_table()
		for e in page_entries:
			bd = disposals.BookedDisposal(e, numeraire)

			numer_proc = bd.total_numeriare_proceeds()
			other_proc = bd.total_other_proceeds_value()
			disposed_cost = bd.total_disposed_cost()
			gain = amount.sub(amount.add(numer_proc, other_proc), disposed_cost)

			(disposed_currency, lots) = check_and_sort_lots(bd.disposal_legs)
			self.renderer.disposal_row(
				e.date, e.narration, numer_proc, other_proc,
				disposed_cost, gain,

				None, None, None, None, # TODO
				# summary.stcg(), cumulative_stcg,
				# summary.ltcg(), cumulative_ltcg,
				disposed_currency, lots)

			self.w(f"USD proceeds: {format_money(bd.total_numeriare_proceeds())}\n")
			for leg in bd.numeraire_proceeds_legs:
				self.w(f"  + {leg.units}\n")

			self.w(f"Other proceeds: total value {format_money(bd.total_other_proceeds_value())}\n")
			for leg in bd.other_proceeds_legs:
				self.w(f"  + {leg.units} value ea {format_money(leg.cost)}\n")
			
			self.w(f"Total disposed cost: {format_money(bd.total_disposed_cost())}\n")
			for leg in bd.disposal_legs:
				id = inventory_idx.lookup_lot_id(leg.account, leg.cost)
				self.w(f"  - {disposals.disposal_inventory_ref(leg, id)}\n")


	def run_mining_summary_subreport(self, title: str, ty: int):
		self.renderer.subreport_header(title)

		# see this: 
		# def iter_entry_dates(entries, date_begin, date_end):
		ty_entries = [e for e in self.entries if e.date.year == ty]

		currency = "XCH"
		mining_stats_by_month = [MiningStats(currency) for _ in range(12)]

		for e in ty_entries:
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
			self.report.write("\n(No mining income)\n")
			return

		# TODO: this one might actually be better rendered by beanquery query rendering....

		self.report.write("\n"
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
			self.report.write(
				f"{calendar.month_abbr[month + 1]:<6}"
				f"{stats.n_events:>8}"
				f"{common.format_money(stats.total_mined, token, 8, 24)}"
				f"{common.format_money(stats.avg_award_size(), token, 8, 20)}"
				f"{common.format_money(cumulative_mined, token, 4, 24)}"
				f"{common.format_money(stats.avg_price(), tok_price_units, 4, 20)}"
				f"{common.format_money(stats.total_fmv, 'USD', 4, 20)}"
				f"{common.format_money(cumulative_fmv, 'USD', 2, 20)}"
				"\n")

		self.report.write(f"\n{'':6}{'':8}"
				f"{'Total cumulative fair market value of all mined tokens:':>{24 + 20 + 24 + 20 + 20}}"
				f"{common.format_money(cumulative_fmv, 'USD', 2, 20)}")