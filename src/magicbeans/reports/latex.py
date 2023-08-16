import datetime
from decimal import Decimal
import textwrap
from typing import List
from beancount.core.amount import Amount
from beancount.core.data import Posting
from beanquery.query_render import render_text
from magicbeans import disposals
from magicbeans.disposals import abbrv_disposal, format_money
from magicbeans.reports.data import AcquisitionsReportRow, DisposalsReport, InventoryReport, MiningSummaryRow

from pylatex import Document, Section, Subsection, Command, LongTabu, Tabu, Center, MultiColumn, MiniPage, TextColor, Package, VerticalSpace, HFill, NewLine
from pylatex.utils import italic, NoEscape, bold
from pylatex.basic import HugeText, LargeText, MediumText, SmallText, NewPage
from pylatex.math import Math


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

def dec8(n) -> str:
	return decn(n, 8)

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
			"margin": "0.3in",
		}

		# TODO: How to do sans-serif font?
		self.doc = Document(
			page_numbers=True,
			font_size="scriptsize",
			lmodern=False,
		    geometry_options=geometry_options)

		self.doc.preamble.append(Command('usepackage', 'helvet'))

		# self.doc.preamble.append(NoEscape(r"\renewc
		# self.doc.preamble.append(Package("helvet"))
		self.doc.preamble.append(NoEscape(r"\renewcommand{\familydefault}{\sfdefault}"))
		self.doc.change_length(r"\tabcolsep", "2pt")

	def close(self):
		self.doc.generate_pdf(self.path, clean_tex=False)

	def write_paragraph(self, text: str):
		self.doc.append(text + "\n\n")

	def write_text(self, text: str):
		self.doc.append(text)

	def header(self, title: str):
		self.doc.append(NewPage())
		self.doc.append(Section(title, numbering=False))
		
	def subheader(self, title: str, q: str = None):
		self.doc.append(Subsection(title, numbering=False))

	def subreport_header(self, title: str, q: str = None):
		self.subheader(title)
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
	# Wrapper
	#

	def details_page(self,
			inventory_report: InventoryReport,
			acquisitions_report_rows: List[AcquisitionsReportRow],
			disposals_report: DisposalsReport):

		with self.doc.create(MiniPage(width=r"0.2\textwidth", pos="t")) as page:
			self.inventory(inventory_report)

		self.doc.append(HFill())
		with self.doc.create(MiniPage(width=r"0.8\textwidth", pos="t")) as page:
			self.acquisitions(acquisitions_report_rows)
			self.doc.append(VerticalSpace("16pt"))
			self.doc.append(NewLine())
			self.disposals(disposals_report)

	#
	# Inventory report
	#

	def inventory(self, inventory_report: InventoryReport):
		if True:
			fmt = "| X[-1l] X[-1rp] X[-1r] X[-1r] |"
			with self.doc.create(Tabu(fmt, pos="t", spread="0pt")) as table:
				table.add_hline()
				table.add_row((MultiColumn(4, align="|c|",
					data=MediumText(f"Starting Inventory")), ))
				if not inventory_report.accounts:
					table.add_hline()
					table.add_row((MultiColumn(4, data="No inventory to report"),))
					table.add_hline()
				for acct in inventory_report.accounts:
					table.add_hline()

					acct_name = acct.account.replace("Assets:Xfer:", "Xfer ")
					table.add_row((MultiColumn(4, data=bold(acct_name)),))
					table.add_hline()

					n_lots = len(acct.positions_and_ids)

					table.add_row((
						"",
						dec6(acct.total.number),
						(MultiColumn(2, align="l|", data=f"total in {n_lots} lot{'s' if n_lots > 1 else ''}")),
						))
					table.add_hline()

					last_line_added = 0
					for (line_no, (pos, lot_id)) in enumerate(acct.positions_and_ids):
						if (line_no < 10 or lot_id):
							ref = disposals.disposal_inventory_ref(pos, lot_id)
							table.add_row((
								lot_id if lot_id else "",
								dec6(pos.units.number),
								dec2(pos.cost.number),
								pos.cost.date))
							last_line_added = line_no
						elif line_no == last_line_added + 1:
							table.add_row((MultiColumn(4, align="|c|", data=NoEscape(r'$\cdots$')),))

				table.add_hline()

	#
	# Acquisitions report
	#

	def acquisitions(self, acquisitions_report_rows: List[AcquisitionsReportRow]):
		width = r"0.8\textwidth"
		fmt = " X[-1l] X[-1l] X[-1r] X[-1l] X[-1r] X[-1r]"
		with self.doc.create(Tabu(fmt, pos="t", spread="0pt")) as table:
			table.add_hline()
			table.add_row((
				"Date",
				"Description",
				MultiColumn(2, data="Assets Acquired", align="r"),
				"Cost ea.",
				"Total cost"
				))
			table.add_hline()

			for row in acquisitions_report_rows:
				table.add_row((
					row.date,
					row.narration,
					dec6(row.amount),
					row.cur,
					dec4(row.cost_ea),
					dec2(row.total_cost),
					))
			
			table.add_hline()

	#
	# Disposals report
	#

	def disposals(self, disposals_report: DisposalsReport):
		if True:
			fmt = "X[-1r] X[-1l] X[-1r] X[-1r] X[-1r] X[-1r] X[-1r] X[-1r] X[-1r]"
			with self.doc.create(Tabu(fmt, pos="t", spread="0pt")) as table:
				table.add_hline()
				table.add_row((
					MultiColumn(1, align="l", data="Date"),   # Just for the align override.
					NoEscape("Description, augmentations (+), disposals with cost ($-$)"),
					"Proceeds",
					"Cost",
					"Gain",
					"STCG",
					"(cumul)",
					"LTCG",
					"(cumul)",
					))

				for (rownum, row) in enumerate(disposals_report.rows):
					if disposals_report.extended or rownum % 5 == 0:
						table.add_hline()
					
					# Put true USD proceeds and FMV of other proceeds in the
					# same column, with the latter italicized.
					proceeds = ""
					if row.numeraire_proceeds:
						proceeds += dec2(row.numeraire_proceeds.number)
					if row.other_proceeds:
						if proceeds:
							proceeds += " + "
						proceeds += italic(dec2(row.other_proceeds.number), escape=False)

						dec2(row.other_proceeds.number),
					table.add_row((
						row.date,
						row.narration,
						NoEscape(proceeds),
						dec2(row.disposed_cost),
						dec2(row.gain),
						dec2(row.stcg),
						TextColor("gray", dec2(row.cum_stcg)),
						dec2(row.ltcg),
						TextColor("gray", dec2(row.cum_ltcg)),
						))

					if disposals_report.extended:
						for leg in row.numeraire_proceeds_legs:
							table.add_row(("+", f"{dec4(leg.units.number)} {leg.units.currency}", "", "", "", "", "", "", ""))

						for leg in row.other_proceeds_legs:
							msg = f"{dec4(leg.units.number)} {leg.units.currency} value ea {dec4(leg.cost.number)}"
							table.add_row(("+", MultiColumn(5, align="l", data=msg), "", "", ""))
						
						for (leg, id) in row.disposal_legs_and_ids:
							msg = f"{disposals.disposal_inventory_ref(leg, id)}"
							table.add_row((NoEscape("$-$"), MultiColumn(5, align="l", data=msg), "", "", ""))


				table.add_hline()

				table.add_row((
					"",
					"Total",
					"",
					"",
					"",
					"",
					dec2(disposals_report.cumulative_stcg),
					"",
					dec2(disposals_report.cumulative_ltcg),
					))

	def mining_summary(self, rows: List[MiningSummaryRow]):
		fmt = "X[-1r] X[-1r] X[-1r] X[-1r] X[-1r] X[-1r] X[-1r] X[-1r]"
		with self.doc.create(Tabu(fmt, pos="t", spread="0pt")) as table:
			table.add_hline()
			table.add_row((
				"Month",
				"#Awards",
				"Amount mined",
				"Avg award size",
				"Cumulative total",
				"Avg. cost",
				"FMV earned",
				"Cumulative FMV"))

			for row in rows:
				tok_price_units = f"USD/{row.currency}"
				table.add_hline()
				table.add_row((
					row.month,
					row.n_awards,
					dec8(row.amount_mined),
					dec8(row.avg_award_size),
					dec4(row.cumul_total),
					dec4(row.avg_cost),
					dec4(row.fmv_earned),
					dec2(row.cumulative_fmv),
					))
				last_row = row

			table.add_hline()
			table.add_row((
				MultiColumn(5, align="r", data="Total cumulative fair market value of all mined tokens:"),
				"", "", dec2(last_row.cumulative_fmv)
			))