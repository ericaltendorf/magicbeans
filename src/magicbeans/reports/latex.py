from typing import List
from beancount.core.amount import Amount
from beanquery.query_render import render_text
from magicbeans import disposals
from magicbeans.disposals import abbrv_disposal, format_money
from magicbeans.reports.data import AcquisitionsReportRow, CoverPage, DisposalsReport, DisposalsReportRow, DisposalsSummary, DisposalsSummaryRow, DisposalsSummaryTotalRow, InventoryReport, MiningSummaryRow, TaxReport

from pylatex import Document, Table, Section, Subsection, Command, Center, MultiColumn, MiniPage, TextColor, Package, VerticalSpace, HFill, NewLine, Tabular, Tabularx, LongTable
from pylatex.base_classes import Environment, Float
from pylatex.utils import italic, NoEscape, bold
from pylatex.basic import HugeText, LargeText, MediumText, SmallText, NewPage
from pylatex.math import Math

# TODO: This truncation probably should take place in the driver.
DEFAULT_NUM_LOTS_PER_ACCT = 8
MAX_DISPLAYED_LOTS_PER_ACCT = 40

# TODO: get the tabudecimal thing working, or maybe siunitx, which is
# already in the tabu pylatex package.
# See: https://jeltef.github.io/PyLaTeX/current/pylatex/pylatex.quantities.html
# adn https://latex-tutorial.com/tutorials/tables/#Align
# or maybe this becomes easier after switching to tblr
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

def table_text(text: str):
	return SmallText(bold(text))

def proceeds_text(row: DisposalsReportRow) -> str:
	proceeds = ""
	if row.numeraire_proceeds:
		proceeds += dec2(row.numeraire_proceeds)
	if row.other_proceeds:
		if proceeds:
			proceeds += " + "
		proceeds += italic(dec2(row.other_proceeds), escape=False)
	return proceeds

# TODO: get rid of these, don't use for summaries

def proceeds_text(row: DisposalsSummaryRow) -> str:
	proceeds = ""
	if row.numeraire_proceeds:
		proceeds += dec2(row.numeraire_proceeds)
	if row.other_proceeds:
		if proceeds:
			proceeds += " + "
		proceeds += italic(dec2(row.other_proceeds), escape=False)
	return proceeds

def proceeds_text(row: DisposalsSummaryTotalRow) -> str:
	proceeds = ""
	if row.numeraire_proceeds:
		proceeds += dec2(row.numeraire_proceeds)
	if row.other_proceeds:
		if proceeds:
			proceeds += " + "
		proceeds += italic(dec2(row.other_proceeds), escape=False)
	return proceeds


class Multicols(Environment):
	packages = [Package('multicol')]
	escape = False
	_latex_name = "multicols*"  # The star prevents column balancing.

class Small(Environment):
	pass

class Tblr(Tabular):
	packages = [Package('tabularray')]

	def __init__(self, colspec, ncols, *args, **kwargs):
		start_args = NoEscape(f"colspec={{ {colspec} }}")
		
		# tabularray/tblr "width" is like a line or text width 
		if 'width' in kwargs:
			start_args = NoEscape(f"width={kwargs['width']},") + start_args
			del kwargs['width']

		# This is the PyLaTeX Tabular class attribute "width", which is a column
		# count, and unrelated to the tblr "width".  In theory this should be
		# computable from the colspec with PyLaTeX's table._get_table_width()
		# function, but that may not properly handle tabularray column/table specs,
		# so instead we just require it be manually specified.
		self.width = ncols

		# some other PyLaTeX Tabular stuff.
		self.booktabs = None
		self.row_height = None
		self.col_space = None

		# We inherit from Tabular, but we bypass its constructor as it makes
		# some assumptions about the start arguments that aren't appropriate for
		# tabularray.
		Environment.__init__(self, options=None, arguments=NoEscape(start_args),
							 *args, **kwargs)

class LaTeXRenderer():
	def __init__(self, path: str) -> None:
		"""Initialize with the PyLaTeX doc to write to."""
		self.path = path
		
		geometry_options = {
			"landscape": False,
			"hmargin": "0.3in",
			"top": "0.3in",
			"bottom": "0.7in",
		}

		self.doc = Document(
			page_numbers=True,
			font_size="scriptsize",
			# font_size="tiny",
			lmodern=False,
		    geometry_options=geometry_options)

		# Use helvetica font
		self.doc.preamble.append(Command('usepackage', 'helvet'))
		self.doc.preamble.append(NoEscape(r"\renewcommand{\familydefault}{\sfdefault}"))
		
		# Paragraph spacing
		self.doc.preamble.append(Command('usepackage', 'parskip'))
		
		# TOC
		self.doc.preamble.append(Command('setcounter', ['tocdepth', '2']))
		self.doc.preamble.append(Command('setcounter', ['secnumdepth', '0']))
		
		# Tables
		self.doc.preamble.append(Command('usepackage', 'arydshln'))
		self.doc.change_length(r"\tabcolsep", "2pt")  # For tabularx
		# self.doc.preamble.append(NoEscape(r"\SetTblrInner{rowsep=0pt,colsep=2pt}"))  # For tblr

		# Needs a package install
		# self.doc.preamble.append(NoEscape(r"\UseTblrLibrary{siunitx}"))  # For number formatting

	def close(self):
		self.doc.generate_pdf(self.path, clean_tex=False)

	def write_paragraph(self, text: str):
		self.doc.append(NoEscape(text))
		self.doc.append("\n\n")

	def write_text(self, text: str):
		self.doc.append(text)

	def newpage(self):
		self.doc.append(NewPage())

	def header(self, title: str):
		self.doc.append(NewPage())
		self.doc.append(Section(NoEscape(title), numbering=True))
		
	def subheader(self, title: str, q: str = None):
		self.doc.append(Subsection(NoEscape(title), numbering=False))

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

	def coverpage(self, page: CoverPage):
		with self.doc.create(Multicols(arguments="2")):
			self.header(page.title)
			with self.doc.create(Small()):
				for line in page.summary_lines:
					self.write_paragraph(line)
				self.write_paragraph(page.text)

				self.doc.append(NoEscape(r"\vfill\null"))
				self.doc.append(NoEscape(r"\columnbreak"))
				self.doc.append(NoEscape(r"\tableofcontents"))

	def details_page(self,
			inventory_report: InventoryReport,
			acquisitions_report_rows: List[AcquisitionsReportRow],
			disposals_report: DisposalsReport):

		with self.doc.create(MiniPage(width=r"0.3\textwidth", pos="t", content_pos="t")) as page:
			# Trick the minipage env to align to this (zero-height) first line
			self.doc.append(NoEscape(r"\vspace{0pt}"))
			self.inventory(inventory_report)

		self.doc.append(HFill())
		with self.doc.create(MiniPage(width=r"0.7\textwidth", pos="t", content_pos="t")) as page:
			# Trick the minipage env to align to this (zero-height) first line
			self.doc.append(NoEscape(r"\vspace{0pt}"))

			# self.doc.append(NoEscape(r"\strut\vspace*{-\baselineskip}\newline"))
			self.acquisitions(acquisitions_report_rows)
			self.doc.append(VerticalSpace("8pt"))
			self.doc.append(NewLine())
			self.disposals_report_detailed("Disposals", disposals_report)

	#
	# Overall tax report
	#

	def tax_report(self, tax_report: TaxReport):
		# This is a small table, can afford to have more legible text
		with self.doc.create(SmallText()):
			wide = ">{\\raggedleft\\arraybackslash}p{4cm}"
			narrow = ">{\\raggedleft\\arraybackslash}p{2cm}"
			with self.doc.create(Tabularx(f"X {wide} {wide} {narrow} {narrow} {narrow} ",
								 width_argument=NoEscape(r"0.95\linewidth" ))) as table:
				table.add_hline()
				table.add_row((
					"Asset",
					"Long term gain/loss",
					"Short term gain/loss",
					"LTCG Tax",
					"STCG Tax",
					"Total Tax",
					))

				for (rownum, row) in enumerate(tax_report.rows):
					if rownum % 5 == 0:
						table.add_hline()
					
					table.add_row((
						row.asset,
						dec2(row.ltcg),
						dec2(row.stcg),
						dec2(row.ltcg_tax),
						dec2(row.stcg_tax),
						dec2(row.total_tax),
						))

				table.add_hline()

				table.add_row((
					"Total",
					dec2(tax_report.total_row.ltcg),
					dec2(tax_report.total_row.stcg),
					dec2(tax_report.total_row.ltcg_tax),
					dec2(tax_report.total_row.stcg_tax),
					dec2(tax_report.total_row.total_tax),
					))
			self.doc.append(NewLine())


	#
	# Inventory report
	#

	def inventory(self, inventory_report: InventoryReport):
		# Estimate how constrained for space we'll be, so we can selectively abbreviate
		# the display of unindexed lots, which are not critical for the report.  This is
		# some sophisticated logic that probably belongs in the driver.

		# Count the number of indexed and unindexed lots per account
		n_indexed_by_acct = {}
		n_unindexed_by_acct = {}
		for a in inventory_report.accounts:
			n_indexed_lots = len([x for x in a.positions_and_ids if x[1]])
			n_indexed_by_acct[a.account] = n_indexed_lots
			n_unindexed_by_acct[a.account] = len(a.positions_and_ids) - n_indexed_lots
			
		# How many rows will we used with a particular max_unindexed_per account?
		def count_rows(n_indexed_lots_by_acct, n_unindexed_lots_by_acct, max_unindexed_per):
			total = 0
			accts = n_indexed_lots_by_acct.keys()
			assert(accts == n_unindexed_lots_by_acct.keys())
			for acct in accts:
				n_indexed = n_indexed_lots_by_acct[acct]
				n_unindexed = n_unindexed_lots_by_acct[acct]
				total += min(n_unindexed, max_unindexed_per) + n_indexed
			return total
		
		# Set the max number of unindexed lots to show by brute force
		max_unindexed_per = max(n_unindexed_by_acct.values()) if n_unindexed_by_acct.values() else 100
		max_rows = 56
		while max_unindexed_per >= 0 and count_rows(n_indexed_by_acct, n_unindexed_by_acct, max_unindexed_per) > max_rows:
			max_unindexed_per -= 1

		# Build the report
		# with self.doc.create(Tblr("|r r r X|", 4, width=r"0.95\linewidth" )) as table:
		with self.doc.create(Tabularx("|r r X r|", width_argument=NoEscape(r"0.95\linewidth") )) as table:
			timestamp_str = inventory_report.ts.strftime("%Y-%m-%d %H:%M:%S UTC")
			table.add_row((MultiColumn(4, align="c",
				data=table_text(f"Inventory {timestamp_str}")), ))
			if not inventory_report.accounts:
				table.add_hline()
				table.add_row((MultiColumn(4, data="No inventory to report"),))
				table.add_hline()
				table.add_row(("", "", "", ""))  # Needed to force the X cell to expand the row
			else:
				table.add_hline()
#
			for a in inventory_report.accounts:
				table.add_row((MultiColumn(4, data=bold(a.account)),))
				table.add_hline()

				n_lots = len(a.positions_and_ids)

				table.add_row((
					dec6(a.total.number),
					(MultiColumn(2, align="l", data=f"total in {n_lots} lot{'s' if n_lots > 1 else ''}")),
					"ID",
					))
				table.add_hline()

				# If we have nothing to show here, don't even render the table.
				if max_unindexed_per <= 0 and n_indexed_by_acct[a.account] == 0:
					continue

				last_line_added = 0
				total_lines_added = 0
				just_showed_ellipsis = False
				for (line_no, (pos, lot_id)) in enumerate(a.positions_and_ids):
					if (line_no < max_unindexed_per or lot_id):
						table.add_row((
							dec6(pos.units.number),
							dec4(pos.cost.number),
							pos.cost.date,
							f"#{lot_id}" if lot_id else "",
							))
						total_lines_added += 1
						last_line_added = line_no
						just_showed_ellipsis = False
					elif not just_showed_ellipsis:
						table.append(Command("hdashline"))
						just_showed_ellipsis = True

				if just_showed_ellipsis:
					table.add_row((MultiColumn(4, align="|c|", data=bold(NoEscape(r'$\cdots$'))),))

				table.add_hline()

	#
	# Acquisitions report
	#

	def acquisitions(self, acquisitions_report_rows: List[AcquisitionsReportRow]):
		# with self.doc.create(Tblr("r X[1,l] l r r r r", 7, width=r"0.95\linewidth" )) as table:
		with self.doc.create(Tabularx("r l r r X r", width_argument=NoEscape(r"0.95\linewidth") )) as table:
			table.add_row((MultiColumn(6, align="c", data=table_text(f"Acquisitions")),))
			table.add_hline()
			table.add_row((
				"Date",
				"",
				"Cost ea.",
				"Total cost",
				"",  # filler column
				"Lot ID",
				))
			table.add_hline()

			for row in acquisitions_report_rows:
				table.add_row((
					row.date,
					f"{dec6(row.amount)} {row.cur}",
					dec4(row.cost_ea),
					dec2(row.total_cost),
					"", # filler column
					f"#{row.lotid}" if row.lotid else "",
					))
				table.add_row(("", 
					MultiColumn(5, align="l", data=TextColor("gray", row.narration)), ))
			
			table.add_hline()

	#
	# Disposals summary and detailed report
	#

	def disposals_summary(self, title: str, disposals_summary: DisposalsSummary):
		# with self.doc.create(Tblr("r X[1,l] r r r r r r r", 9, width=r"0.95\linewidth" )) as table:
		cspec = ">{\\raggedleft\\arraybackslash}p{1.6cm}"
		with self.doc.create(Tabularx("r r r X" + f" {cspec}" * 7, width_argument=NoEscape(r"0.95\linewidth" ))) as table:
			table.add_row((MultiColumn(11, align="c", data=table_text(title)),))
			table.add_hline()
			table.add_row((
				"Assets",
				"Date Acquired",
				"Date Disposed",
				"", # filler
				"Proceeds",
				"Cost",
				"Gain",
				"STCG",
				"(cumul)",
				"LTCG",
				"(cumul)",
				))

			for (rownum, row) in enumerate(disposals_summary.rows):
				if rownum % 5 == 0:
					table.add_hline()
				
				table.add_row((
					f"{dec4(row.disposed_amount)} {row.disposed_currency}",
					row.acquisition_date,
					row.date,
					"", # filler
					dec2(row.numeraire_proceeds + row.other_proceeds),
					dec2(row.disposed_cost),
					dec2(row.gain),
					dec2(row.stcg),
					TextColor("gray", dec2(row.cum_stcg)),
					dec2(row.ltcg),
					TextColor("gray", dec2(row.cum_ltcg)),
					))

			table.add_hline()

			trow = disposals_summary.total_row
			table.add_row((
				(MultiColumn(3, align="r", data=f"Total: {dec8(trow.disposed_amount)} ")),
				"", # filler
				dec2(trow.numeraire_proceeds + trow.other_proceeds),
				dec2(trow.disposed_cost),
				dec2(trow.gain),
				dec2(trow.stcg),
				"",
				dec2(trow.ltcg),
				"",
				))
		self.doc.append(NewLine())

	def disposals_report_detailed(self, title: str, disposals_report: DisposalsReport):
		# with self.doc.create(Tblr("r X[1,l] r r r r r r r", 9, width=r"0.95\linewidth" )) as table:
		with self.doc.create(Tabularx("r X r r r r r r r", width_argument=NoEscape(r"0.95\linewidth" ))) as table:
			table.add_row((MultiColumn(9, align="c", data=table_text(title)),))
			table.add_hline()
			table.add_row((
				MultiColumn(1, align="l", data="Date"),   # Just for the align override.
				"", #NoEscape("Description" + (", legs ($+$, $-$)" if disposals_report.show_details else "")),
				"Proceeds",
				"Cost",
				"Gain",
				"STCG",
				"(cumul)",
				"LTCG",
				"(cumul)",
				))

			for (rownum, row) in enumerate(disposals_report.rows):
				if disposals_report.show_details or rownum % 5 == 0:
					table.add_hline()
				
				table.add_row((
					row.date,
					f"{dec4(row.disposed_amount)} {row.disposed_currency}",
					NoEscape(proceeds_text(row)),
					dec2(row.disposed_cost),
					dec2(row.gain),
					dec2(row.stcg),
					TextColor("gray", dec2(row.cum_stcg)),
					dec2(row.ltcg),
					TextColor("gray", dec2(row.cum_ltcg)),
					))
				table.add_row(("", 
					MultiColumn(8, align="l", data=TextColor("gray", row.narration)), ))

				for leg in row.numeraire_proceeds_legs:
					table.add_row((NoEscape("$+$"), f"{dec4(leg.units.number)} {leg.units.currency}", "", "", "", "", "", "", ""))

				for leg in row.other_proceeds_legs:
					msg = f"{dec4(leg.units.number)} {leg.units.currency} value ea {dec4(leg.cost.number)}"
					table.add_row((NoEscape("$+$"), MultiColumn(5, align="l", data=msg), "", "", ""))
				
				for (i, (leg, id)) in enumerate(row.disposal_legs_and_ids):
					# Negated since we render a special neg sign separate from the number.
					msg = f"{disposals.disposal_inventory_ref_neg(leg, id)}"
					# TODO: is there a more pythonic way to do this?
					if i == len(row.disposal_legs_and_ids) - 1 and row.num_legs_omitted > 0:
						msg = msg + f", and {row.num_legs_omitted} more (smaller) lot(s)"
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
		self.doc.append(NewLine())

	def mining_summary(self, rows: List[MiningSummaryRow]):
		cwide = ">{\\raggedleft\\arraybackslash}p{2.4cm}"
		cnarr = ">{\\raggedleft\\arraybackslash}p{1.0cm}"
		cmid = ">{\\raggedleft\\arraybackslash}X"
		with self.doc.create(Tabularx(f"{cnarr} {cnarr} {cwide} {cnarr} {cwide}" + f" {cmid}" * 4, width_argument=NoEscape(r"0.95\linewidth" ))) as table:
			table.add_hline()
			table.add_row((
				"Month",
				"#Awards",
				"Amount mined",
				"Asset",
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
					row.currency,
					dec8(row.avg_award_size),
					dec4(row.cumul_total),
					dec4(row.avg_cost),
					dec4(row.fmv_earned),
					dec2(row.cumulative_fmv),
					))
				last_row = row

			table.add_hline()
			table.add_row((
				MultiColumn(6, align="r", data="Total cumulative fair market value of all mined tokens:"),
				"", "", dec2(last_row.cumulative_fmv)
			))