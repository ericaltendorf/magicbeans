from contextlib import contextmanager
import datetime
from decimal import Decimal
import textwrap
from typing import List
from beancount.core.amount import Amount
from beancount.core.data import Posting
from beanquery.query_render import render_text
from magicbeans import disposals
from magicbeans.disposals import abbrv_disposal, format_money
from magicbeans.reports.data import AccountInventoryReport, InventoryReport

class TextRenderer():
	def __init__(self, file) -> None:
		"""Initialize with the file to write to."""
		self.file = file

	def write_text(self, text: str):
		self.file.write(text)

	# TODO: parameterize the width of this header, probably
	# via an argument on ReportDriver.
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
