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
from magicbeans.disposals import BookedDisposal, format_money, get_disposal_postings, is_disposal_tx, is_other_proceeds_leg, mk_disposal_summary, sum_amounts, LotIndex
from magicbeans.mining import MINING_BENEFICIARY_ACCOUNT, MINING_INCOME_ACCOUNT, MiningStats, is_mining_tx
from magicbeans.reports.data import AcquisitionsReportRow, CoverPage, DisposalsReport, DisposalsReportRow, AccountInventoryReport, InventoryReport, MiningSummaryRow
from magicbeans.reports.latex import LaTeXRenderer
from magicbeans.reports.text import TextRenderer

from beancount import loader
from beancount.core.amount import Amount
from beancount.parser import parser
from beanquery.query import run_query
from beanquery.query_render import render_text


def beancount_quarter(ty: int, quarter_n: int):
	return f"{ty}-Q{quarter_n}"

MAX_DISPOSAL_LEGS = 40

REPORT_ABSTRACT = """\
The first section of this report contains annual summaries.  For each year, it shows
asset disposals, the proceeds, and the short and long term capital gains or losses
(gains shown as positive numbers, losses as negative).

The second section contains more detailed summaries of activity during each
year.  Each year is broken down into periods containing one page's worth of
activity.  Each period (i.e., page) shows: (1) the starting inventory (the set
of held lots for each type of asset), (2) pure acquisitions (receipt of assets
in exchange for USD payment, i.e., nontaxable events), and finally (3) disposals,
i.e., receipt of USD or other assets of value, in exchange for the disposal of
some other assets of value.

This disposals table identifies the received or augmented assets.  If these assets
are USD, the USD amount is shown as "Proceeds".  If the assets are not USD, then
the "Proceeds" column is italicized and shows the fair market value of the
received assets at the time of receipt.  For example, if 1 BTC were exchanged for
10,000 USDT (Tether), the proceeds column might show "10,007" or something
similar, since the value of USDT can fluctuate slightly around 1 USD.

The disposals table also identifies the disposed lots.  It shows the quantity of
assets from that lot, and identifies the lot by the original cost basis (per unit)
and date of acquisition.  To facilitate auditing, where possible the report will
show a "lot ID" for the disposed lot, to cross reference against either the
starting inventory table, or previous transactions (e.g., acquisitions, transfers,
or disposals).  This lot ID is unique only within one page of the report.

Finally, the disposals table shows the sum of the cost bases of all disposed lots
in the "Cost" column, and in additional columns, the overall gain and loss, 
the short term and long term capital gains/losses, and the cumulative totals.

The third and final section (perhaps omitted in abbreviated versions of the report)
contains a complete history of all mining rewards, for reference.
"""

class ReportDriver:
	"""Wraps a beancount file and facilitates reporting with BQL queries.

	Initialize the driver with the path to the beancount file and the path to
	the output report file.  Then call the other methods to run queries and
	write the results to the report file.
	"""	

	# TODO: query(), render(), and query_and_render() may be obsolete now.

	def __init__(self, ledger_path: str, out_path: str, numeraire: str) -> None:
		"""Load the beancount file at the given path and parse it for queries, 
		and initialize the output report file."""
		
		# self.renderer = TextRenderer(out_path)
		self.renderer = LaTeXRenderer(out_path)

		entries, _errors, options = loader.load_file(ledger_path)
		self.entries = entries
		self.options = options

		self.numeraire = numeraire
	
	def write_text(self, text: str):
		"""Legacy function to allow caller to write direclty to underlying file"""
		self.renderer.write_text(text)
	
	def close(self):
		self.renderer.close()

	def coverpage(self, timestamp: datetime.date,
				  tax_years: List[int], cryptos: List[str]):
		page = CoverPage("Magicbeans Tax Report", [
			f"Generated {timestamp}",
			f"Covering tax years {', '.join([str(ty) for ty in tax_years])}",
			f"Reporting on cryptocurrencies {', '.join(cryptos)}"
		   ],
		   REPORT_ABSTRACT)
		self.renderer.coverpage(page)

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

	#
	# High level reporting functions
	#
	def tax_year_summary(self, ty: int):
		self.renderer.header(f"{ty} Tax Summary")
		self.run_disposals_summary(datetime.date(ty, 1, 1), datetime.date(ty+1, 1, 1))
		self.run_mining_summary(f"{ty} Mining Operations and Income", ty)

	#
	# New report methods, using direct analysis of the entries
	#

	def get_inventory_and_entries(self, start: datetime.date, end: datetime.date):
		"""For a time period, get the inventory at the start and all entries in the period"""
		(inventories_by_acct, index) = summarize.balance_by_account(
			self.entries, start)

		# Remove numeraire-only accounts; we don't need to track those
		for (account, inventory) in list(inventories_by_acct.items()):
			if all([p.units.currency == self.numeraire for p in inventory]):
				inventories_by_acct.pop(account)

		# Define the list of transactions to process in this period
		all_entries = summarize.truncate(self.entries[index:], end)

		# TODO: could we construct the inventory index here and return it?  does
		# the caller really need this raw inventories_by_acct dict?
		return (inventories_by_acct, all_entries)

	def make_inventory_report(self, start, inventory_blocks, lot_index):
		"""Construct an inventory report object."""
		account_inventory_reports = [] 
		for (cur, account, positions) in inventory_blocks:
			# TODO: Hiding these for now to avoid taking up space, but we should really 
			# track them down and figure out why there's assets remaining in these accounts.
			if account.startswith("Assets:Xfer:"):
				continue

			total = sum_amounts(cur, [pos.units for pos in positions])

			acct_inv_rep = AccountInventoryReport(account, total, [])
			for pos in positions:
				lotid = lot_index.get_lotid(pos.units.currency, pos.cost)
				acct_inv_rep.positions_and_ids.append((pos, lotid))
			account_inventory_reports.append(acct_inv_rep)
		return InventoryReport(start, account_inventory_reports)

	def make_acquisitions_report(self, acquisitions, mining_awards, lot_index):
		"""Construct a list of acquisition report rows."""
		period_mining_stats = MiningStats("XCH")   # TODO: generalize!

		acquisitions_report_rows = []
		for e in acquisitions:
			# This should be safe, should have been checked by is_acquisition_tx()
			rcvd = next(filter(lambda p: is_other_proceeds_leg(p, self.numeraire), e.postings))
			acquisitions_report_rows.append(AcquisitionsReportRow(
				e.date, e.narration, rcvd.units.number, rcvd.units.currency,
				rcvd.cost.number, rcvd.cost.number * rcvd.units.number,
				lot_index.get_lotid(rcvd.units.currency, rcvd.cost)
			))
		
		for e in mining_awards:
			accrue_mining_stats(e, period_mining_stats)

		if mining_awards:
			acquisitions_report_rows.append(AcquisitionsReportRow(
				"Various",
				f"Mining rewards ({period_mining_stats.n_events} transactions, cost ea. reported as average)",
				period_mining_stats.total_mined,
				period_mining_stats.currency,
				period_mining_stats.avg_price(),
				period_mining_stats.total_fmv, None))
		return acquisitions_report_rows

	def make_disposals_report(self, booked_disposals, lot_index, start, end, show_legs):
		# Collect disposal transactions referencing IDs
		cumulative_stcg = Decimal("0")
		cumulative_ltcg = Decimal("0")
		disposals_report_rows = []
		for bd in booked_disposals:
			numer_proc = bd.total_numeriare_proceeds()
			other_proc = bd.total_other_proceeds_value()
			disposed_cost = bd.total_disposed_cost()
			gain = amount.sub(amount.add(numer_proc, other_proc), disposed_cost)
			cumulative_stcg += bd.stcg()
			cumulative_ltcg += bd.ltcg()

			disposal_legs_and_ids = []
			num_legs_omitted = 0
			if show_legs:
				disposal_legs_and_ids = [
					(p, lot_index.get_lotid(p.units.currency, p.cost))
					for p in bd.disposal_legs]
				n_legs = len(disposal_legs_and_ids)
				disposal_legs_and_ids = disposal_legs_and_ids[:MAX_DISPOSAL_LEGS]
				num_legs_omitted = n_legs - len(disposal_legs_and_ids)

			disposals_report_rows.append(DisposalsReportRow(
				bd.tx.date, bd.tx.narration, numer_proc, other_proc, disposed_cost, gain,
				bd.stcg(), cumulative_stcg, bd.ltcg(), cumulative_ltcg,
				bd.disposed_currency,
				bd.numeraire_proceeds_legs,
				bd.other_proceeds_legs,
				disposal_legs_and_ids,
				num_legs_omitted))
		
		return DisposalsReport(start, end, self.numeraire,
				disposals_report_rows, cumulative_stcg, cumulative_ltcg, show_legs)
	
	def run_disposals_summary(self, start: datetime.date, end: datetime.date):
		"""Generate a summary of disposals for the period."""
		inclusive_end = end - datetime.timedelta(days=1)
		if start.year != inclusive_end.year:
			raise ValueError(f"Start and end dates must be in same tax year: {start}, {end}")
		ty = start.year

		# Get the disposals to report.  (Given disposals are all we need, there might be a 
		# simpler way to obtain them.)
		(inventories_by_acct, all_entries) = self.get_inventory_and_entries(start, end)
		all_txs = list(filter(lambda x: isinstance(x, Transaction), all_entries))
		(disposals, acquisitions, mining_awards) = self.partition_entries(all_txs, self.numeraire)
		booked_disposals = [BookedDisposal(e, self.numeraire) for e in disposals]

		disposed_assets = set([bd.disposed_asset() for bd in booked_disposals])

		self.renderer.subheader(f"Disposals and Gain/Loss, {start}--{inclusive_end}")
		if not disposed_assets:
			self.renderer.write_text("(No disposals in this period.)")
			return	

		for asset in disposed_assets:
			disposals_for_asset = [bd for bd in booked_disposals if bd.disposed_asset() == asset]
			disposals_report = self.make_disposals_report(disposals_for_asset, None, start, end, False)
			self.renderer.disposals(f"{asset} Disposals", disposals_report)

	def run_detailed_log(self, start: datetime.date, end: datetime.date):
		"""Generate a detailed log report of activity during the period."""
		inclusive_end = end - datetime.timedelta(days=1)
		if start.year != inclusive_end.year:
			raise ValueError(f"Start and end dates must be in same tax year: {start}, {end}")
		ty = start.year

		# This is a little confusing -- we'll call get_inventory_and_entries()
		# multiple times; the first time for the entire period, to get all
		# entries, and then subsequent times to get an inventory for the date
		# for each page.
		(_, all_entries) = self.get_inventory_and_entries(start, end)
		all_txs = list(filter(lambda x: isinstance(x, Transaction), all_entries))

		pages = list(paginate_entries(all_txs, 40))
		for page_num in range(len(pages)):
			tx_page = pages[page_num]
			page_start = (start if page_num == 0 else tx_page[0].date)
			page_end = (inclusive_end if page_num == len(pages) - 1
			   else max(tx_page[-1].date, pages[page_num + 1][0].date - datetime.timedelta(days=1)))

			# Partition entries into disposals, acquisitions, and mining awards
			(disposals, acquisitions, mining_awards) = self.partition_entries(tx_page, self.numeraire)

			# inventories_by_acct is a dict mapping account names to inventories, which
			# in turn are dicts mapping currencies to lists of positions.
			(inventories_by_acct, _) = self.get_inventory_and_entries(page_start, page_end)

			# First organize inventories by currency, and sort, so that we can
			# assign lot IDs in order.
			inventory_blocks = []  # (currency, account, positions) tuples
			for acct in inventories_by_acct.keys():
				for (cur, positions) in inventories_by_acct[acct].split().items():
					inventory_blocks.append((cur, acct,
							  sorted(positions, key=lambda x: -abs(x.units.number))))
			inventory_blocks.sort()

			# Collect inventory and acquisition reports
			# Populate the lot index, and assign IDs to the interesting lots
			lot_index = LotIndex(inventory_blocks, acquisitions, disposals, self.numeraire)
			inv_report = self.make_inventory_report(page_start, inventory_blocks, lot_index)
			acquisitions_report_rows = self.make_acquisitions_report(acquisitions, mining_awards, lot_index)

			booked_disposals = [BookedDisposal(e, self.numeraire) for e in disposals]
			disposals_report = self.make_disposals_report(booked_disposals, lot_index, page_start, page_end, True)
		
			# Render.
			n_pages = len(pages)
			self.renderer.header(
				f"{ty} Detailed Activity Log ({page_num+1}/{n_pages}) "
				+ f"{page_start.strftime('%m-%d')}--{page_end.strftime('%m-%d')}")
			self.renderer.details_page(inv_report, acquisitions_report_rows, disposals_report)

	def run_mining_summary(self, title: str, ty: int):
		self.renderer.subreport_header(title)

		# see this: 
		# def iter_entry_dates(entries, date_begin, date_end):
		ty_entries = [e for e in self.entries if e.date.year == ty]

		currency = "XCH"
		mining_stats_by_month = [MiningStats(currency) for _ in range(12)]

		found_mining_tx = False
		for e in ty_entries:
			if is_mining_tx(e):
				found_mining_tx = True
				month = e.date.month - 1
				accrue_mining_stats(e, mining_stats_by_month[month])

		if not found_mining_tx:
			self.renderer.write_text("(No mining transactions in this period.)")
			return

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

def paginate_entries(entries, page_size: int):
	"""Yield lists of entries which fit on one page."""
	page_start_index = 0
	vweight = 0  # Roughly, number of table lines used.
	for i in range(0, len(entries)):
		row_weight = 0
		if not is_mining_tx(entries[i]):
			row_weight += 1
		if is_disposal_tx(entries[i]):
			row_weight += len(entries[i].postings)

		if vweight + row_weight > page_size:
			if i == page_start_index:
				# We went overweight on the first entry.  Just yield it anyway.
				yield entries[page_start_index:i+1]
				page_start_index = i+1
				vweight = 0
			else:
				yield entries[page_start_index:i]
				page_start_index = i
				vweight = row_weight
		else:
			vweight += row_weight

	if page_start_index < len(entries):
		yield entries[page_start_index:]

def accrue_mining_stats(mining_tx, stats_to_update):
	income_posting = common.maybe_get_unique_posting_by_account(
		mining_tx, MINING_INCOME_ACCOUNT)
	if income_posting and income_posting.units.currency != "USD":
		raise ValueError(f"Unexpected currency: {income_posting.units.currency}")

	beneficiary_posting = common.get_unique_posting_by_account(
		mining_tx, MINING_BENEFICIARY_ACCOUNT)
	if beneficiary_posting.units.currency != "XCH":
		raise ValueError(f"Unexpected currency: {beneficiary_posting.units.currency}")

	stats_to_update.n_events += 1
	stats_to_update.total_mined += Decimal(beneficiary_posting.units.number)
	if income_posting:
		stats_to_update.total_fmv -= Decimal(income_posting.units.number)