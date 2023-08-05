from enum import Enum
import subprocess
import sys
from typing import List
from beancount.core.amount import Amount
from beanquery.query_render import render_text
from pyfiglet import Figlet
from beancount import loader

from beancount.parser import parser
from beanquery.query import run_query
from tabulate import tabulate
from magicbeans import reports
from magicbeans import queries

#
# Report generation helpers
#

def subreport_header(title: str, q: str):
	# TODO: move this into ReportDriver?
	return " " + ("_" * 98) + f" \n|{title:_^98}|\n\n{q}\n\n"

# TODO: this doesn't really work; each column data is typed so you can't
# just replace it with a ditto character. 
def ditto_fields(rtypes, rrows, id_col, ditto_cols):
	last_id = None
	for row in rrows:
		this_id = rrows[id_col]
		if this_id == last_id:
			for col in ditto_cols:
				row[col] = row[col]._replace(value = "  ''")
		last_id = this_id

def quarter_report(year: int, quarter_n: int, currencies: List[str], db):
	quarter = reports.beancount_quarter(year, quarter_n)
	quarter_begin = f"""{ty}-{["01", "04", "07", "10"][quarter_n-1]}-01"""
	currency_re = "|".join(currencies)

	db.report.write(f.renderText(f"{year} Q {quarter_n}"))

	q =	queries.inventory(quarter_begin, currency_re)
	db.report.write(subreport_header(f"Inventory as of {quarter_begin}", q))
	db.query_and_render(q)

	q = queries.disposals(quarter)
	db.report.write(subreport_header(f"Disposals in {quarter}", q))
	db.query_and_render(q)

	q = queries.pnl(quarter)
	db.report.write(subreport_header(f"Profit and loss in {quarter}", q))
	db.query_and_render(q, footer="Note: this is an income account; neg values are gains and pos values are losses.")

	q = queries.acquisitions(quarter, currency_re)
	db.report.write(subreport_header(f"Acquisitions in {quarter}", q))
	db.query_and_render(q)
	
	q = queries.mining_summary(quarter, currency_re)
	db.report.write(subreport_header(f"Mining summary for {quarter}", q))
	db.query_and_render(q)


if __name__ == '__main__':
	ledger_path = sys.argv[1]   # "build/final.beancount"
	out_path = sys.argv[2]   # "build/report.txt"

	print(f"Generating report for beancount file {ledger_path} and writing to {out_path}")
	db = reports.ReportDriver(ledger_path, out_path)

	# TODO: move figlet into ReportDriver?
	f = Figlet(width=120)

	# TODO: move to a config
	currencies = ["BTC", "ETH", "LTC", "XCH"]
	tax_years = range(2018, 2022 + 1)

	print("Generating tax summaries:")
	for ty in tax_years:
		print(f"  {ty}", end="", flush=True)
		db.report.write(f.renderText(f"{ty} Tax Summary"))

		q = queries.year_large_disposals(ty)
		db.report.write(subreport_header(f"Large Disposals", q))
		db.query_and_render(q)

		q = queries.year_small_disposals(ty)
		db.report.write(subreport_header(f"Small Disposals (aggregated by quarter)", q))
		db.query_and_render(q)

		q = queries.year_mining_income_by_quarter(ty)
		db.report.write(subreport_header(f"Mining Income By Quarter", q))
		db.query_and_render(q, footer="For more detail see full mining history at end of report.")

		q = queries.year_mining_income_total(ty)
		db.report.write(subreport_header(f"Mining Income Year Total", q))
		db.query_and_render(q, footer="Note: this is an income account; neg values are gains and pos values are losses.")
	print()

	db.report.write(f.renderText("Quarterly Operations"))
	print("Generating quarterly operations reports:")
	for ty in tax_years:
		print(f"  {ty} ", end="", flush=True)
		for quarter_n in [1, 2, 3, 4]:
			print(f"{quarter_n} ", end="", flush=True)
			quarter_report(ty, quarter_n, currencies, db)
	print()

	db.report.write(f.renderText("Full Mining History"))
	currency_re = "|".join(currencies)  # TODO: dup code
	print("Generating full mining history:")
	for ty in tax_years[2:]:
		print(f"  {ty} ", end="", flush=True)
		for quarter_n in [1, 2, 3, 4]:
			print(f"{quarter_n} ", end="", flush=True)
			quarter = reports.beancount_quarter(ty, quarter_n)
			q = queries.mining_full(quarter, currency_re)
			db.report.write(subreport_header(f"Mining in {quarter}", q))
			db.query_and_render(q)
	print()

