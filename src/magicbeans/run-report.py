import datetime
import subprocess
import sys
from enum import Enum
from typing import List
from beancount.core.data import Posting, Transaction
from beancount.core.inventory import Inventory
from beancount.ops.summarize import balance_by_account
from magicbeans.config import Config
from magicbeans.reports import driver

from pyfiglet import Figlet
from tabulate import tabulate

from beancount import loader
from beancount.core.amount import Amount
from beancount.parser import parser
from beanquery.query import run_query
from beanquery.query_render import render_text
from magicbeans import disposals, queries

#
# Report generation helpers
#

def quarter_start(year: int, quarter_n: int) -> datetime.date:
	return datetime.date(year, (quarter_n-1)*3 + 1, 1)

def quarter_end(year: int, quarter_n: int) -> datetime.date:
	if quarter_n == 4:
		return datetime.date(year+1, 1, 1)
	else:
		return datetime.date(year, quarter_n*3 + 1, 1)

def quarter_report(year: int, quarter_n: int, currencies: List[str], db):
	quarter = driver.beancount_quarter(year, quarter_n)
	quarter_begin = f"""{ty}-{["01", "04", "07", "10"][quarter_n-1]}-01"""
	currency_re = "|".join(currencies)

	db.write_text(f.renderText(f"{year} Q {quarter_n}"))

	db.run_subreport(
		f"Inventory as of {quarter_begin}",
		queries.inventory(quarter_begin, currency_re))
	db.run_subreport(
		f"Disposals in {quarter}",
		queries.disposals(quarter))
	# TODO:  replace this with something like  run_disposals_report() 
	# db.run_subreport(
	# 	f"Profit and loss in {quarter}",
	# 	queries.pnl(quarter),
	# 	footer="Note: this is an income account; neg values are gains and pos values are losses.")
	db.run_subreport(
		f"Acquisitions in {quarter}",
		queries.acquisitions(quarter, currency_re))
	# TODO:  fold this into acquisitions somehow?
	db.run_subreport(
		f"Mining summary for {quarter}",
		queries.mining_summary(quarter, currency_re))

if __name__ == '__main__':
	ledger_path = sys.argv[1]   # "build/final.beancount"
	out_path = sys.argv[2]   # "build/report.txt"
	config = Config()  # Report generation barely uses this, but it's probably OK since
	                   # we'll combine this file with run.py at some point anyway.

	print(f"Generating report for beancount file {ledger_path} "
          f"and writing to {out_path}")
	db = driver.ReportDriver(ledger_path, out_path)

	currencies = config.get_covered_currencies()
	tax_years = range(2018, 2022 + 1)

	db.preamble(datetime.datetime.now(), tax_years, currencies)

	print("Generating tax summaries:")
	for ty in tax_years:
		print(f"  {ty}", end="", flush=True)
		db.renderer.header(f"{ty} Tax Summary")
		db.renderer.subheader("Asset Disposals and Capital Gains/Losses")
		db.disposals(datetime.date(ty, 1, 1), datetime.date(ty+1, 1, 1), False)
		db.run_mining_summary_subreport("Mining Operations and Income", ty)

	print()

	db.renderer.header("Quarterly Operations")
	print("Generating quarterly operations reports:")
	for ty in tax_years:
		print(f"  {ty} ", end="", flush=True)
		for q in [1, 2, 3, 4]:
			print(f"{q} ", end="", flush=True)
			start = quarter_start(ty, q)
			db.renderer.header(f"{ty} Q {q}")
			db.disposals(quarter_start(ty, q), quarter_end(ty, q), True)

	print()

	# db.write_text(f.renderText("Full Mining History"))
	# currency_re = "|".join(currencies)  # TODO: dup code
	# print("Generating full mining history:")
	# for ty in tax_years[0:]:
		# print(f"  {ty} ", end="", flush=True)
		# for quarter_n in [1, 2, 3, 4]:
			# print(f"{quarter_n} ", end="", flush=True)
			# quarter = reports.beancount_quarter(ty, quarter_n)
			# db.run_subreport(
				# f"Mining in {quarter}",
				# queries.mining_full(quarter, currency_re))
	# print()

	db.close()
