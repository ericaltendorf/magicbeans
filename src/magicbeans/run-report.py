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

def quarter_report(year: int, quarter_n: int, currencies: List[str], db):
	quarter = reports.beancount_quarter(year, quarter_n)
	quarter_begin = f"""{ty}-{["01", "04", "07", "10"][quarter_n-1]}-01"""
	currency_re = "|".join(currencies)

	db.report.write(f.renderText(f"{year} Q {quarter_n}"))

	db.run_subreport(
		f"Inventory as of {quarter_begin}",
		queries.inventory(quarter_begin, currency_re))
	db.run_subreport(
		f"Disposals in {quarter}",
		queries.disposals(quarter))
	db.run_subreport(
		f"Profit and loss in {quarter}",
		queries.pnl(quarter),
		footer="Note: this is an income account; neg values are gains and pos values are losses.")
	db.run_subreport(
		f"Acquisitions in {quarter}",
		queries.acquisitions(quarter, currency_re))
	db.run_subreport(
		f"Mining summary for {quarter}",
		queries.mining_summary(quarter, currency_re))


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

		db.run_subreport(
			"Large Disposals",
			queries.year_large_disposals(ty))
		db.run_subreport(
			f"Small Disposals (aggregated by quarter)",
			queries.year_small_disposals(ty))
		db.run_subreport(
			f"Mining Income By Quarter",
			queries.year_mining_income_by_quarter(ty),
			footer="For more detail see full mining history at end of report.")
		db.run_subreport(
			f"Mining Income Year Total",
			queries.year_mining_income_total(ty),
			footer="Note: this is an income account; neg values are gains and pos values are losses.")
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
			db.run_subreport(
				f"Mining in {quarter}",
				queries.mining_full(quarter, currency_re))
	print()

