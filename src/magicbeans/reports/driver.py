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
from magicbeans.reports.data import DisposalsReport, DisposalsReportRow, AccountInventoryReport, InventoryReport, MiningSummaryRow
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


	# TODO: unittest
	def paginate_entries(self, start: datetime.date, end: datetime.date, page_size: int):
		"""Yield dates which segment the provide entries into groups containing at
		   most page_size entries, unless more than that many entries occur on one day."""
		entered_range = False
		last_partition = 0
		last_date_change = 0
		filtered_entries = list(filter(is_disposal_tx, self.entries))
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
				if i - last_partition >= page_size and last_partition != last_date_change:
					yield filtered_entries[last_date_change].date
					last_partition = last_date_change

	#
	# High level reporting functions
	#
	def tax_year_summary(self, ty: int):
		self.renderer.header(f"{ty} Tax Summary")
		self.renderer.subheader("Asset Disposals and Capital Gains/Losses")
		self.disposals(datetime.date(ty, 1, 1), datetime.date(ty+1, 1, 1), False)
		self.mining_summary("Mining Operations and Income", ty)

	#
	# New report methods, using direct analysis of the entries
	#

	def disposals(self, start: datetime.date, end: datetime.date, extended: bool):
		if extended:
			self.renderer.header(f"{start} - {end - datetime.timedelta(days=1)}")
		else:
			self.renderer.subheader(f"{start} - {end - datetime.timedelta(days=1)}")

		first_disposal_after_start = next(filter(
			lambda e: is_disposal_tx(e) and e.date >= start, self.entries))
		first_disposal_date = first_disposal_after_start.date
	
		numeraire = "USD"

		(account_to_inventory, index) = summarize.balance_by_account(
			self.entries, first_disposal_date)

		# Remove numeraire-only accounts; we don't need to track those
		for (account, inventory) in list(account_to_inventory.items()):
			if all([p.units.currency == numeraire for p in inventory]):
				account_to_inventory.pop(account)

		# Define the inventory and get it set up for indexing
		inventory_idx = disposals.ReductionIndexedInventory(account_to_inventory)

		# Define the list of transactions to process on this page
		all_entries = summarize.truncate(self.entries[index:], end)
		page_entries = list(filter(is_disposal_tx, all_entries))
		non_mining_entries = list(filter(lambda e: not is_mining_tx(e), all_entries))
		print(f"Num entries for year: {len(all_entries)}, num disposals: {len(page_entries)}, "
			f"num non-mining entries: {len(non_mining_entries)}")

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
		if extended:
			account_inventory_reports = [] 
			for account in inventory_idx.get_accounts():
				currency_to_inventory = account_to_inventory[account].split()
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
			inv_report = InventoryReport(first_disposal_date, account_inventory_reports)

			self.renderer.inventory(inv_report)

		# Write disposal transactions referencing IDs
		cumulative_stcg = Decimal("0")
		cumulative_ltcg = Decimal("0")
		disposals_report_rows = []
		for e in page_entries:
			bd = disposals.BookedDisposal(e, numeraire)

			numer_proc = bd.total_numeriare_proceeds()
			other_proc = bd.total_other_proceeds_value()
			disposed_cost = bd.total_disposed_cost()
			gain = amount.sub(amount.add(numer_proc, other_proc), disposed_cost)
			cumulative_stcg += bd.stcg()
			cumulative_ltcg += bd.ltcg()

			(disposed_currency, lots) = check_and_sort_lots(bd.disposal_legs)
			disposal_legs_and_ids = [
				(p, inventory_idx.lookup_lot_id(p.account, p.cost))
			    for p in bd.disposal_legs]

			disposals_report_rows.append(DisposalsReportRow(
				e.date, e.narration, numer_proc, other_proc, disposed_cost, gain,
				bd.stcg(), cumulative_stcg, bd.ltcg(), cumulative_ltcg,
				disposed_currency,
				bd.numeraire_proceeds_legs,
				bd.other_proceeds_legs,
				disposal_legs_and_ids))
		
		disposals_report = DisposalsReport(start, end, numeraire,
				disposals_report_rows, cumulative_stcg, cumulative_ltcg, extended)
		
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