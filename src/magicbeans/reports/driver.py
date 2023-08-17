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
from magicbeans.disposals import BookedDisposal, format_money, get_disposal_postings, is_disposal_tx, mk_disposal_summary, sum_amounts, ReductionIndexedInventory
from magicbeans.mining import MINING_BENEFICIARY_ACCOUNT, MINING_INCOME_ACCOUNT, MiningStats, is_mining_tx
from magicbeans.reports.data import AcquisitionsReportRow, DisposalsReport, DisposalsReportRow, AccountInventoryReport, InventoryReport, MiningSummaryRow
from magicbeans.reports.latex import LaTeXRenderer
from magicbeans.reports.text import TextRenderer

from beancount import loader
from beancount.core.amount import Amount
from beancount.parser import parser
from beanquery.query import run_query
from beanquery.query_render import render_text


def beancount_quarter(ty: int, quarter_n: int):
	return f"{ty}-Q{quarter_n}"

REPORT_ABSTRACT = """\
The first section of this report contains annual summaries.  For each year, it shows
asset disposals, specifying the lots disposed (their size, original per-unit cost, and
date of acquisition), the proceeds, and the short and long term capital gains or losses
(gains shown as positive numbers, losses as negative).

The second section contains more detailed quarterly summaries.  At each quarter, we show
the starting inventory (the set of held lots for each type of asset).  Then we show
disposals of assets, followed by new acquisitions of assets via purchase, and finally a
summary assets acquired via mining.

The third and final section contains a complete history of all mining rewards, for
reference.
"""

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
		
		# self.renderer = TextRenderer(out_path)
		self.renderer = LaTeXRenderer(out_path)

		entries, _errors, options = loader.load_file(ledger_path)
		self.entries = entries
		self.options = options
	
	def write_text(self, text: str):
		"""Legacy function to allow caller to write direclty to underlying file"""
		self.renderer.write_text(text)
	
	def close(self):
		self.renderer.close()

	def preamble(self, timestamp: datetime.date,
				 tax_years: List[int], cryptos: List[str]):
		self.renderer.header("Magicbeans Tax Report")
		self.renderer.write_paragraph(f"Generated {timestamp}")
		tys_str = ", ".join([str(ty) for ty in tax_years])
		self.renderer.write_paragraph(f"Covering tax years {tys_str}")
		self.renderer.write_paragraph(f"Reporting on cryptocurrencies {', '.join(cryptos)}")
		self.renderer.write_paragraph(REPORT_ABSTRACT)
	
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
	# Utilities for managing entries
	#

	# TODO: consoldiate this with is_disposal_tx() and is_mining_tx()
	def is_acquisition_tx(self, e: Transaction, numeraire: str):
		"""Return true if the given transaction is an acquisition of an asset."""
		if not isinstance(e, Transaction):
			return False
		if is_mining_tx(e):
			return False
		if len(e.postings) != 2:
			return False
		if len([p for p in e.postings if p.units.currency != numeraire]) != 1:
			return False
		if len([p for p in e.postings if p.units.currency == numeraire]) != 1:
			return False
		return True

	def partition_entries(self, entries, numeraire: str):
		"""Return a tuple of entry lists, one for each type of entry:
		disposals, non-mining acquisitions, and mining acquisitions."""
		disposals = list(filter(is_disposal_tx, entries))
		mining_awards = list(filter(is_mining_tx, entries))
		acquisitions = list(filter(lambda e: self.is_acquisition_tx(e, numeraire), entries))
		return (disposals, acquisitions, mining_awards)

	# TODO: unittest
	def paginate_entries(self, start: datetime.date, end: datetime.date, page_size: int):
		"""Yield dates which segment the provide entries into groups intended to fit on
		   one page.  The supplied 
		   most page_size entries, unless more than that many entries occur on one day.
		   This is currently called from the run script, which then uses the pages to 
		   call disposals_report() for each page, which is all a bit confusing. """
		entered_range = False
		last_partition = 0
		last_date_change = 0
		numeraire = "USD"  # TODO: a hack!
		filtered_entries = list(filter(lambda x: is_disposal_tx(x) or self.is_acquisition_tx(x, numeraire), self.entries))
		vweight = 0  # Accumulate vertical space taken by entries
		for i in range(0, len(filtered_entries)):
			if not entered_range and filtered_entries[i].date >= start:
				entered_range = True
				last_partition = i
				last_date_change = i

			if entered_range:
				if filtered_entries[i].date > end:
					break
				if i > 0 and filtered_entries[i].date != filtered_entries[i-1].date:
					last_date_change = i

				vweight += 1
				if is_disposal_tx(filtered_entries[i]):
					vweight += len(filtered_entries[i].postings)

				if vweight >= page_size and last_partition != last_date_change:
					yield filtered_entries[last_date_change].date
					last_partition = last_date_change
					vweight = 0

	#
	# High level reporting functions
	#
	def tax_year_summary(self, ty: int):
		self.renderer.header(f"{ty} Tax Summary")
		self.disposals_report(datetime.date(ty, 1, 1), datetime.date(ty+1, 1, 1), False)
		self.mining_summary("Mining Operations and Income", ty)

	#
	# New report methods, using direct analysis of the entries
	#

	def get_inventory_and_entries(self, start: datetime.date, end: datetime.date, numeraire: str):
		"""For a time period, get the inventory at the start and all entries in the period"""
		(inventories_by_acct, index) = summarize.balance_by_account(
			self.entries, start)

		# Remove numeraire-only accounts; we don't need to track those
		for (account, inventory) in list(inventories_by_acct.items()):
			if all([p.units.currency == numeraire for p in inventory]):
				inventories_by_acct.pop(account)

		# Define the list of transactions to process on this page
		all_entries = summarize.truncate(self.entries[index:], end)

		# TODO: could we construct the inventory index here and return it?  does
		# the caller really need this raw inventories_by_acct dict?
		return (inventories_by_acct, all_entries)

 	# TODO: this isn't just disposals anymore, it's inventory, acquisitions,
 	# and disposals.  rename
	def disposals_report(self, start: datetime.date, end: datetime.date, extended: bool):
		inclusive_end = end - datetime.timedelta(days=1)
		if start.year != inclusive_end.year:
			raise ValueError(f"Start and end dates must be in same tax year: {start}, {end}")
		ty = start.year

		if extended:   # This logic maybe belongs in the renderer?
			self.renderer.header(
				f"{ty} Inventory, Acquisitions, and Disposals, {start} - {inclusive_end}")
		else:
			self.renderer.subheader(
				f"Asset Disposals and Capital Gains/Losses, {start} - {inclusive_end}")

		numeraire = "USD"

		# Get inventory (balances) at start, and entries for [start, end)
		(inventories_by_acct, all_entries) = self.get_inventory_and_entries(start, end, numeraire)

		# Partition entries into disposals, acquisitions, and mining awards
		(disposals, acquisitions, mining_awards) = self.partition_entries(all_entries, numeraire)

		# Define the inventory and get it set up for indexing
		inventory_idx = ReductionIndexedInventory(inventories_by_acct)

		# Index reduced lots with IDs
		for e in disposals:
			for p in get_disposal_postings(e):
				account = p.account
				if inventory_idx.index_contains(account, p.cost):
					lot_id = inventory_idx.index_lot(account, p.cost)

		# Collect inventory and acquisition reports
		if extended:
			account_inventory_reports = [] 
			for account in inventory_idx.get_accounts():
				currency_to_inventory = inventories_by_acct[account].split()
				for (cur, inventory) in currency_to_inventory.items():
					items = inventory_idx.get_inventory_w_ids(account)
					total = sum_amounts(cur, [pos.units for (pos, id) in items])
					# TODO: this is incorrect
					total_cost = None # sum_amounts(numeraire, [pos.cost for (pos, id) in items])
					acct_inv_rep = AccountInventoryReport(account, total, total_cost, [])
					sorted_pairs = sorted(items, key=lambda x: -abs(x[0].units.number))
					for (pos, lot_id) in sorted_pairs:
						acct_inv_rep.positions_and_ids.append((pos, lot_id))
					account_inventory_reports.append(acct_inv_rep)
				account_inventory_reports.sort(key=lambda x: (x.total.currency, x.account))
			inv_report = InventoryReport(start, account_inventory_reports)

			acquisitions_report_rows = []
			for e in acquisitions:
				# These should be safe, should have been checked by is_acquisition_tx()
				rcvd = [p for p in e.postings if p.units.currency != numeraire][0]
				sent = [p for p in e.postings if p.units.currency == numeraire][0]
				acquisitions_report_rows.append(AcquisitionsReportRow(
					e.date, e.narration, rcvd.units.number, rcvd.units.currency,
					rcvd.cost.number, rcvd.cost.number * rcvd.units.number
				))

		# Collect disposal transactions referencing IDs
		cumulative_stcg = Decimal("0")
		cumulative_ltcg = Decimal("0")
		disposals_report_rows = []
		for e in disposals:
			bd = BookedDisposal(e, numeraire)

			numer_proc = bd.total_numeriare_proceeds()
			other_proc = bd.total_other_proceeds_value()
			disposed_cost = bd.total_disposed_cost()
			gain = amount.sub(amount.add(numer_proc, other_proc), disposed_cost)
			cumulative_stcg += bd.stcg()
			cumulative_ltcg += bd.ltcg()

			disposal_legs_and_ids = [
				(p, inventory_idx.lookup_lot_id(p.account, p.cost))
			    for p in bd.disposal_legs]

			disposals_report_rows.append(DisposalsReportRow(
				e.date, e.narration, numer_proc, other_proc, disposed_cost, gain,
				bd.stcg(), cumulative_stcg, bd.ltcg(), cumulative_ltcg,
				bd.disposed_currency,
				bd.numeraire_proceeds_legs,
				bd.other_proceeds_legs,
				disposal_legs_and_ids))
		
		disposals_report = DisposalsReport(start, end, numeraire,
				disposals_report_rows, cumulative_stcg, cumulative_ltcg, extended)
		
		# Render.
		if extended:
			self.renderer.details_page(inv_report, acquisitions_report_rows, disposals_report)
		else:
			self.renderer.disposals(disposals_report)

	def mining_summary(self, title: str, ty: int):
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

		rows = []

		# TODO: MiningSummaryRow and MiningStats are pretty similar.  Collapse?
		cumulative_mined = Decimal(0)
		cumulative_fmv = Decimal(0)
		for (month, stats) in enumerate(mining_stats_by_month):
			cumulative_mined += stats.total_mined
			cumulative_fmv += stats.total_fmv
			rows.append(MiningSummaryRow(
				currency,
				month + 1,
				stats.n_events,
				stats.total_mined,
				stats.avg_award_size(),
				cumulative_mined,
				stats.avg_price(),
				stats.total_fmv,
				cumulative_fmv))
		
		self.renderer.mining_summary(rows)