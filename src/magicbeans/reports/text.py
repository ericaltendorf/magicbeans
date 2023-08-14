import datetime
from decimal import Decimal
import textwrap
from typing import List
from beancount.core.amount import Amount
from beancount.core.data import Posting
from beanquery.query_render import render_text
from magicbeans import disposals
from magicbeans.disposals import abbrv_disposal, format_money


class TextRenderer():
	def __init__(self, file) -> None:
		"""Initialize with the file to write to."""
		self.file = file

	def write_text(self, text: str):
		self.file.write(text)

	# TODO: parameterize the width of this header, probably
	# via an argument on ReportDriver.
	def subreport_header(self, title: str, q: str = None):
		# TODO: move this into ReportDriver?
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

	def start_inventory_table(self, date: datetime.date):
		self.file.write(f"Inventories as of {date}\n\n")

	def start_inventory_account(self, account: str, currency: str, total: Amount):
		self.file.write(f"{account} {currency} total: {total}\n")

	def inventory_row(self, pos: Posting, lot_id: str):
		self.file.write(f"  {disposals.disposal_inventory_desc(pos, lot_id)}\n")

	def end_inventory_table(self):
		self.file.write("\n")

	#
	# Disposals report
	#

	def start_disposals_table(self):
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

	def disposal_row(self,
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
	def end_disposals_table(self, cum_numer_proceeds: Decimal, cum_other_proceeds: Decimal,
	      					cum_cost, cum_gain,
							cumulative_stcg: Decimal, cumulative_ltcg: Decimal):
		self.file.write("\n")
		self.file.write(
			f"\n{'':<10} {'Total':<64} "
			f"{cum_numer_proceeds:>10.2f} "
			f"{cum_other_proceeds:>10.2f} "
			f"{cum_cost:>10} "
			f"{cum_gain:>10} "
			f"{'STCG':>10} "
			f"{cumulative_stcg:>11.2f} "
			f"{'LTCG':>10} "
			f"{cumulative_ltcg:>11.2f}\n")
