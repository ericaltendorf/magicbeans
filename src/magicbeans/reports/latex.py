import datetime
from decimal import Decimal
import textwrap
from typing import List
from beancount.core.amount import Amount
from beancount.core.data import Posting
from beanquery.query_render import render_text
from magicbeans import disposals
from magicbeans.disposals import abbrv_disposal, format_money
from magicbeans.reports.data import DisposalsReport, InventoryReport

from pylatex import Document, Section, Subsection, Command, LongTabu, Tabu, Center, MultiColumn
from pylatex.utils import italic, NoEscape, bold
from pylatex.basic import HugeText, LargeText, MediumText, SmallText, NewPage


# TODO: get the tabudecimal thing working, or maybe siunitx, which is
# already in the tabu pylatex package.
# See: https://jeltef.github.io/PyLaTeX/current/pylatex/pylatex.quantities.html
# adn https://latex-tutorial.com/tutorials/tables/#Align
def dec2(n) -> str:
	return decn(n, 2)
def dec4(n) -> str:
	return decn(n, 4)
def dec6(n) -> str:
	return decn(n, 6)
def decn(n, d):
	if not n:
		return ""
	if isinstance(n, Amount):
		n = n.number
	return f"{n:.{d}f}"


class LaTeXRenderer():
	def __init__(self, path: str) -> None:
		"""Initialize with the PyLaTeX doc to write to."""
		self.path = path
		
		geometry_options = {
			"landscape": True,
			"margin": "0.4in",
		}

		# TODO: How to do sans-serif font?
		self.doc = Document(
			page_numbers=True,
			font_size="scriptsize",
		    geometry_options=geometry_options)
		self.doc.change_length(r"\columnsep", "0.5in")

	def close(self):
		self.doc.generate_pdf(self.path, clean_tex=False)

	def write_paragraph(self, text: str):
		self.doc.append(text + "\n\n")

	def write_text(self, text: str):
		self.doc.append(text)

	def header(self, title: str):
		self.doc.append(NewPage())
		self.doc.append(LargeText(title) + "\n\n")
		
	def subheader(self, title: str, q: str = None):
		self.subreport_header(title, q)

	# TODO: parameterize the width of this header, probably
	# via an argument on ReportDriver.
	def subreport_header(self, title: str, q: str = None):
		self.doc.append(MediumText(title) + "\n\n")
		if q:
			self.doc.append('Query: {q}')

	def beanquery_table(self, rtypes, rrows, footer=None):
		"""Render the results of a beanquery query as a table"""

		# if len(rrows) > 0:
		# 	render_text(rtypes, rrows, self.options['dcontext'], self.file,
		# 				expand=True, boxed=False, narrow=False)
		# 	if footer:
		# 		self.file.write("\n" + footer + "\n")
		# else:
		# 	self.file.write('(None)\n')

		# self.file.write('\n')
		pass

	#
	# Inventory report
	#

	def inventory(self, inventory_report: InventoryReport):
		fmt = "| X[-1l] X[-1rp] X[-1r] X[-1r] |"
		with self.doc.create(Tabu(fmt, spread="0pt")) as table:
			table.add_hline()
			table.add_row((MultiColumn(4,
				data=MediumText(f"Inventory as of {inventory_report.date}\n")), ))
			for acct in inventory_report.accounts:
				table.add_hline()

				table.add_row((MultiColumn(4, data=bold(acct.account)),))
				table.add_hline()

				last_line_added = 0
				for (line_no, (pos, lot_id)) in enumerate(acct.positions_and_ids):
					if (line_no < 12 or lot_id):
						ref = disposals.disposal_inventory_ref(pos, lot_id)
						table.add_row((
							lot_id if lot_id else "",
							dec6(pos.units.number),
							dec2(pos.cost.number),
							pos.cost.date))
						last_line_added = line_no
					elif line_no == last_line_added + 1:
						table.add_row((MultiColumn(4, data=NoEscape(r'\cdots')),))


				table.add_hline()
				table.add_row((
					"",
					dec6(acct.total.number),
					"",  # TODO: This isn't set correctly : dec2(acct.total_cost.number),
					"Total"))
			table.add_hline()

	#
	# Disposals report
	#

	def disposals(self, disposals_report: DisposalsReport):
		fmt = " X[-1r] X[-1l] X[-1r] X[-1r] X[-1r] X[-1r] X[-1r] X[-1r] X[-1r] X[-1r]"
		with self.doc.create(Tabu(fmt, spread="0pt")) as table:
			table.add_hline()
			table.add_row((
				"Date",
				"Narration",
				"Proceeds",
				"Other, FMV",
				"Cost",
				"Gain",
				"STCG",
				"(cumul)",
				"LTCG",
				"(cumul)",
				))

			for (rownum, row) in enumerate(disposals_report.rows):
				if rownum % 1 == 0:
					table.add_hline()
				table.add_row((
					row.date,
					row.narration[:20] + "...",  # Hack for now
					dec2(row.numeraire_proceeds.number),
					dec2(row.other_proceeds.number),
					dec2(row.disposed_cost),
					dec2(row.gain),
					dec2(row.stcg),
					dec2(row.cum_stcg),
					dec2(row.ltcg),
					dec2(row.cum_ltcg),
					))

				if disposals_report.extended:
					for leg in row.numeraire_proceeds_legs:
						table.add_row(("+", leg.units, "", "", "", "", "", "", "", ""))

					for leg in row.other_proceeds_legs:
						msg = f"{leg.units} value ea {dec4(leg.cost.number)}"
						table.add_row(("+", MultiColumn(6, align="l", data=msg), "", "", ""))
					
					for (leg, id) in row.disposal_legs_and_ids:
						msg = f"{disposals.disposal_inventory_ref(leg, id)}"
						table.add_row(("-", MultiColumn(6, align="l", data=msg), "", "", ""))


			table.add_hline()

			table.add_row((
				"",
				"Total",
				"",
				"",
				"",
				"",
				"",
				dec2(disposals_report.cumulative_stcg),
				"",
				dec2(disposals_report.cumulative_ltcg),
				))

