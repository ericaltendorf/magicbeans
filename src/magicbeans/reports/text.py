import datetime
from decimal import Decimal
import textwrap
from typing import List
from beancount.core.data import Posting
from beanquery.query_render import render_text
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

	def start_disposals_table(self):
		self.file.write(
			f"{'Date':<10} {'Narration':<74} "
			f"{'Proceeds':>10} "
			f"{'STCG':>10} "
			f"{'Cumulative':>11} "
			f"{'LTCG':>10} "
			f"{'Cumulative':>11}\n\n")

	def disposal_row(self, date: datetime.date, narration: str, proceeds: Decimal,
					 stcg: Decimal, cumulative_stcg: Decimal,
					 ltcg: Decimal, cumulative_ltcg: Decimal,
					 disposed_currency: str, lots: List[Posting]):

		# TODO: why do i have to call str(summary.date)??
		self.file.write(
			f"{str(date):<10} {narration:.<74.74} "
			f"{format_money(proceeds):>10} "
			f"{format_money(stcg):>10} "
			f"{cumulative_stcg:>11.2f} "
			f"{format_money(ltcg):>10} "
			f"{cumulative_ltcg:>11.2f}\n")
		
		# TODO: abbrv_disposal probably shouldn't be over there
		rendered_lots = (f"{disposed_currency} " +
						 ", ".join([abbrv_disposal(d) for d in lots]))

		self.file.write("\n".join(textwrap.wrap(
			f"Disposed lots: {rendered_lots}",
			width=74, initial_indent="           ", subsequent_indent="           ")))
		self.file.write("\n")

	def end_disposals_table(self, cumulative_proceeds: Decimal,
							cumulative_stcg: Decimal, cumulative_ltcg: Decimal):
		self.file.write("\n")
		self.file.write(
			f"\n{'':<10} {'Total':<74} "
			f"{cumulative_proceeds:>10.2f} "
			f"{'STCG':>10} "
			f"{cumulative_stcg:>11.2f} "
			f"{'LTCG':>10} "
			f"{cumulative_ltcg:>11.2f}\n")
