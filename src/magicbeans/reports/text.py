import calendar
from contextlib import contextmanager
import datetime
from decimal import Decimal
import textwrap
from typing import List
from beancount.core.amount import Amount
from beancount.core.data import Posting
from beanquery.query_render import render_text
from magicbeans import common, disposals
from magicbeans.disposals import abbrv_disposal, format_money
from magicbeans.reports.data import AccountInventoryReport, InventoryReport
from pyfiglet import Figlet

# TODO: parameterize the width of this report
class TextRenderer():
	def __init__(self, out_path) -> None:
		"""Initialize with the file to write to."""
		# TODO: verify this is closed on destruction
		self.file = open(out_path, 'w')
		self.fig = Figlet(width=120)

	def close(self):
		self.file.close()

	def write_paragraph(self, text: str):
		self.file.write(text + "\n\n")

	def write_text(self, text: str):
		self.file.write(text)

	def header(self, title: str):
		self.file.write(self.fig.renderText(title))
		
	def subheader(self, title: str, q: str = None):
		self.subreport_header(title, q)

	def subreport_header(self, title: str, q: str = None):
		result = " " + ("_" * 140) + f" \n|{title:_^140}|\n"
		if q:
			# Text wrapping is useful if you're consuming as a text file;
			#   if you convert to PDF that will wrap for you.
			# result += "\n".join(textwrap.wrap(q, width=140,
			#       initial_indent="", subsequent_indent="  ")) + "\n"
			result += q + "\n"
		self.file.write(result)

	def beanquery_table(self, rtypes, rrows, footer=None):
		"""Render the results of a beanquery query as a table"""

		if len(rrows) > 0:
			render_text(rtypes, rrows, self.options['dcontext'], self.file,
						expand=True, boxed=False, narrow=False)
			if footer:
				self.file.write("\n" + footer + "\n")
		else:
			self.file.write('(None)\n')

		self.file.write('\n')

	#
	# Inventory report
	#

	def inventory(self, inventory_report: InventoryReport):
		self.file.write(f"Inventories as of {inventory_report.date}\n\n")
		for acct in inventory_report.accounts:
			self.file.write(f"{acct.account} total: {acct.total}\n")
			for (pos, lot_id) in acct.positions_and_ids:
				self.file.write(f"  {disposals.disposal_inventory_desc(pos, lot_id)}\n")
		self.file.write("\n")

	#
	# Disposals report
	#

	def disposals(self, disposals_report):
		self._start_disposals_table()
		for row in disposals_report.rows:
			self._disposal_row(
				row.date, row.narration,
				row.numeraire_proceeds, row.other_proceeds, row.disposed_cost,
				row.gain, row.stcg, row.cum_stcg, row.ltcg, row.cum_ltcg,
				row.disposed_currency, [p[0] for p in row.disposal_legs_and_ids])
			if disposals_report.extended:
				self.file.write(f"USD proceeds: {format_money(row.numeraire_proceeds)}\n")
				for leg in row.numeraire_proceeds_legs:
					self.file.write(f"  + {leg.units}\n")

				self.file.write(f"Other proceeds: total value {format_money(row.other_proceeds)}\n")
				for leg in row.other_proceeds_legs:
					self.file.write(f"  + {leg.units} value ea {format_money(leg.cost)}\n")
				
				self.file.write(f"Total disposed cost: {format_money(row.disposed_cost)}\n")
				for (leg, id) in row.disposal_legs_and_ids:
					self.file.write(f"  - {disposals.disposal_inventory_ref(leg, id)}\n")

	def _start_disposals_table(self):
		self.file.write(
			f"{'':<10} {'':<64} "
			f"{'Proceeds value':>20} "
			f"{'':>20} "
			f"{'Short term':>21} "
			f"{'Long term':>21}\n")
		self.file.write(
			f"{'Date':<10} {'Narration':<64} "
			f"{'USD':>10} "
			f"{'other':>10} "
			f"{'Cost':>10} "   # New
			f"{'Gain':>10} "   # New
			f"{'Gains':>10} "
			f"{'Cumul.':>11} "
			f"{'Gains':>10} "
			f"{'Cumul.':>11}\n\n")

	def _disposal_row(self,
			date: datetime.date, narration: str,
			numer_proceeds: Decimal, other_proceeds: Decimal,
			cost: Decimal, gain: Decimal,
			stcg: Decimal, cumulative_stcg: Decimal,
			ltcg: Decimal, cumulative_ltcg: Decimal,
			disposed_currency: str, lots: List[Posting]):

		# TODO: why do i have to call str(summary.date)??
		self.file.write(
			f"{str(date):<10} {narration:.<64.64} "
			f"{format_money(numer_proceeds):>10} "
			f"{format_money(other_proceeds):>10} "
			f"{format_money(cost):>10} "
			f"{format_money(gain):>10} "
			f"{format_money(stcg):>10} "
			f"{format_money(cumulative_stcg):>11} "
			f"{format_money(ltcg):>10} "
			f"{format_money(cumulative_ltcg):>11}\n")
		
		# TODO: abbrv_disposal probably shouldn't be over there
		rendered_lots = (f"{disposed_currency} " +
						 ", ".join([abbrv_disposal(d) for d in lots]))

		self.file.write("\n".join(textwrap.wrap(
			f"Disposed lots: {rendered_lots}",
			width=64, initial_indent="           ", subsequent_indent="           ")))
		self.file.write("\n")

	# Use amount?  use format_money() ?
	def _end_disposals_table(self,
			cum_numer_proceeds: Decimal, cum_other_proceeds: Decimal,
	       	cum_cost, cum_gain, cum_stcg: Decimal, cum_ltcg: Decimal):
		self.file.write("\n")
		self.file.write(
			f"\n{'':<10} {'Total':<64} "
			f"{cum_numer_proceeds:>10.2f} "
			f"{cum_other_proceeds:>10.2f} "
			f"{cum_cost:>10} "
			f"{cum_gain:>10} "
			f"{'STCG':>10} "
			f"{cum_stcg:>11.2f} "
			f"{'LTCG':>10} "
			f"{cum_ltcg:>11.2f}\n")


	# TODO: placeholder pseudocode, untested
	def mining_summary(self, rows: List[MiningSummaryRow]):
		self.write_text("\n"
			f"{'Month':<6}"
			f"{'#Awards':>8}"
			f"{'Amount mined':>24}"
			f"{'Avg award size':>20}"
			f"{'Cumulative total':>24}"
			f"{'Avg. cost':>20}"
			f"{'FMV earned':>20}"
			f"{'Cumulative FMV':>20}\n\n")

		if len(rows) == 0:
			self.write_text("\n(No mining income)\n")
			return

		for row in rows:
			tok_price_units = f"USD/{token}"
			self.write_text(
				f"{calendar.month_abbr[row.month + 1]:<6}"
				f"{row.n_events:>8}"
				f"{common.format_money(row.total_mined, token, 8, 24)}"
				f"{common.format_money(row.avg_award_size(), token, 8, 20)}"
				f"{common.format_money(row.cumulative_mined, token, 4, 24)}"
				f"{common.format_money(row.avg_price(), tok_price_units, 4, 20)}"
				f"{common.format_money(row.total_fmv, 'USD', 4, 20)}"
				f"{common.format_money(row.cumulative_fmv, 'USD', 2, 20)}"
				"\n")
			last_row = row  # Remember the last row for printing the summary line

		self.write_text(f"\n{'':6}{'':8}"
				f"{'Total cumulative fair market value of all mined tokens:':>{24 + 20 + 24 + 20 + 20}}"
				f"{common.format_money(last_row.cumulative_fmv, 'USD', 2, 20)}")
		self.write_text("\n\n")