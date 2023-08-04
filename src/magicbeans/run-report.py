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

class ReportDriver:
	"""Simple wrapper around a beancount database facilitating bean-query queries
	and writing the results to a file."""

	def __init__(self, ledger_path: str, out_path: str) -> None:
		"""Load the beancount file at the given path and parse it for queries, 
		and initialize the output report file."""
		self.report = open(out_path, 'w')   # TODO: verify this is closed on destruction

		entries, _errors, options = loader.load_file(ledger_path)
		self.entries = entries
		self.options = options
	
	def query(self, query: str):
		"""Run a bean-query query on the entries in this database.  Returns a
		list of (name, dtype) tuples describing the results set table and a list
		of ResultRow tuples with the data.item pairs."""
		return run_query(self.entries, self.options, query)

	def render(self, rtypes, rrows):
		render_text(rtypes, rrows, self.options['dcontext'], self.report,
	      			expand=True, boxed=False, narrow=False)

	def query_and_render(self, query: str, footer: str = None):
		(rtypes, rrows) = self.query(query)
		if len(rrows) > 0:
			self.render(rtypes, rrows)
			if footer:
				self.report.write("\n" + footer + "\n")
		else:
			self.report.write('(None)\n')

		self.report.write('\n')

#
# Queries
# TODO: parameterize the account names out of these queries
#

def q_fees(ty: int):
	return (
		f'SELECT account, sum(position)'
	    f'FROM has_account("Fees") OPEN ON {ty}-01-01 CLOSE ON {ty+1}-01-01'
		f'WHERE account ~ "Fees" ')

def q_inventory(date: str, currency_re: str):
	return (
		f'SELECT account, SUM(position) as lots, '
		f'UNITS(SUM(position)) AS total, COST(SUM(position)) AS total_cost '
		f'FROM has_account("Assets") CLOSE ON {date} '
		f'WHERE currency~"{currency_re}" ')

def q_disposals(quarter: str):
	return (
		f'SELECT date, narration, account, '
		f'units(position) as amount, '
		f'round(number(cost(position)) / number(units(position)), 4) as cost_each, '
		f'cost(position) as total_cost ' 
		f'FROM has_account("PnL") and quarter(date) = "{quarter}" ')

def q_acquisitions(quarter: str, currency_re: str):
	# This has query code in common with q_disposals(); consider refactoring.
	return (
		f'SELECT date, narration, account, '
		f'units(position) as amount, '
		f'round(number(cost(position)) / number(units(position)), 4) as cost_each, '
		f'cost(position) as total_cost ' 
		f'FROM quarter(date) = "{quarter}" '
		f'AND NOT has_account("Income:Mining") '
		f'WHERE number > 0 and currency~"{currency_re}" ')

def q_mining_summary(quarter: str, currency_re: str):
	return (
		f'SELECT units(sum(position)) '
		f'FROM quarter(date) = "{quarter}" AND has_account("Income:Mining")')

def q_mining_full(quarter: str, currency_re: str):
	# This has query code in common with q_disposals(); consider refactoring.
	return (
		f'SELECT date, entry_meta("timestamp") as timestamp_utc, narration, '
		f'units(position) as amount, '
		f'units(sum(balance)) as run_total, '
		f'round(number(cost(position)) / number(units(position)), 4) as cost_ea, '
		f'cost(position) as cost, ' 
		f'cost(sum(balance)) as run_total_cost ' 
		f'FROM quarter(date) = "{quarter}" '
		f'AND has_account("Income:Mining") '
		f'WHERE number > 0 and currency~"{currency_re}" ')

def q_pnl(quarter: str):
	return (
		f'SELECT date, narration, account, cost(position) as amount, balance '
		f'FROM has_account("PnL") AND quarter(date) = "{quarter}" '
		f'WHERE account="Income:PnL"')

#
# Report generation helpers
#

def quarter_str(year: int, quarter_n: int):
	return f"{ty}-Q{quarter_n}"

def subreport_header(title: str, q: str):
	return f"##########  {title}  ##########\n\n{q}\n\n"

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
	quarter = quarter_str(year, quarter_n)
	quarter_begin = f"""{ty}-{["01", "04", "07", "10"][quarter_n-1]}-01"""
	currency_re = "|".join(currencies)

	db.report.write(f.renderText(f"-- {year} Q {quarter_n} --"))

	db.report.write(f.renderText("Inventory"))

	q =	q_inventory(quarter_begin, currency_re)
	db.report.write(subreport_header(f"Inventory as of {quarter_begin}", q))
	db.query_and_render(q)

	db.report.write(f.renderText(f"Transactions & PnL"))

	q = q_disposals(quarter)
	db.report.write(subreport_header(f"Disposals in {quarter}", q))
	db.query_and_render(q)

	q = q_pnl(quarter)
	db.report.write(subreport_header(f"Profit and loss in {quarter}", q))
	db.query_and_render(q, footer="Note: this is an income account; neg values are gains and pos values are losses.")

	q = q_acquisitions(quarter, currency_re)
	db.report.write(subreport_header(f"Acquisitions in {quarter}", q))
	db.query_and_render(q)
	
	q = q_mining_summary(quarter, currency_re)
	db.report.write(subreport_header(f"Mining summary for {quarter}", q))
	db.query_and_render(q)


if __name__ == '__main__':
	ledger_path = sys.argv[1]   # "build/final.beancount"
	out_path = sys.argv[2]   # "build/report.txt"

	print(f"Generating report for beancount file {ledger_path} and writing to {out_path}")
	db = ReportDriver(ledger_path, out_path)

	# TODO: move figlet into ReportDriver?
	f = Figlet(width=120)

	# TODO: move to a config
	currencies = ["BTC", "ETH", "LTC", "XCH"]
	tax_years = range(2018, 2022 + 1)

	db.report.write(f.renderText("Quarterly Operations"))
	for ty in tax_years:
		for quarter_n in [1, 2, 3, 4]:
			quarter_report(ty, quarter_n, currencies, db)

	db.report.write(f.renderText("Full Mining History"))
	currency_re = "|".join(currencies)  # TODO: dup code
	for ty in tax_years[2:]:
		for quarter_n in [1, 2, 3, 4]:
			quarter = quarter_str(ty, quarter_n)
			q = q_mining_full(quarter, currency_re)
			db.report.write(subreport_header(f"Mining in {quarter}", q))
			db.query_and_render(q)

