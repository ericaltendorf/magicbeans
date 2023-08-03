from enum import Enum
import subprocess
import sys
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

	def query_and_render(self, query: str):
		(rtypes, rrows) = self.query(query)
		self.render(rtypes, rrows)
		self.report.write('\n')

#
# Queries
#

def q_fees(ty: int):
	return (
		f'SELECT account, sum(position)'
	    f'FROM has_account("Fees") OPEN ON {ty}-01-01 CLOSE ON {ty+1}-01-01'
		f'WHERE account ~ "Fees" ')

def q_inventory(date: str, currency_re: str):
	return (
		f'SELECT account, SUM(position) as lots, '
		f'UNITS(SUM(position)) AS Total, COST(SUM(position)) AS totalcost '
		f'FROM has_account("Assets") CLOSE ON {date} '
		f'WHERE currency~"{currency_re}" ')

def q_disposals(quarter: str):
	return (
		f'SELECT date, narration, account, '
		f'units(position) as amount, '
		f'round(number(cost(position)) / number(units(position)), 4) as costeach, '
		f'cost(position) as totalcost ' 
		f'FROM has_account("PnL") and quarter(date) = "{quarter}" ')

def q_acquisitions(quarter: str, currency_re: str):
	# This has query code in common with q_disposals(); consider refactoring.
	return (
		f'SELECT date, narration, account, '
		f'units(position) as amount, '
		f'round(number(cost(position)) / number(units(position)), 4) as costeach, '
		f'cost(position) as totalcost ' 
		f'FROM quarter(date) = "{quarter}" '
		f'WHERE number > 0 and currency~"{currency_re}" ')

def q_pnl(quarter: str):
	return (
		f'SELECT date, narration, account, cost(position) as amount, balance '
		f'FROM has_account("PnL") AND quarter(date) = "{quarter}" '
		f'WHERE account="Income:PnL"')

#
# Report generation helpers
#

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

def quarter_report(year: int, quarter_n: int, db):
	quarter = f"{ty}-Q{quarter_n}"
	quarter_begin = f"""{ty}-{["01", "04", "07", "10"][quarter_n-1]}-01"""
	currency_re = "BTC|ETH|LTC|XCH"

	db.report.write(f.renderText(f"{year} Q {quarter_n} : inventory"))

	q =	q_inventory(quarter_begin, currency_re)
	db.report.write(subreport_header(f"Inventory as of {quarter_begin}", q))
	db.query_and_render(q)

	db.report.write(f.renderText(f"{year} Q {quarter_n} : transactions & PnL"))

	q = q_disposals(quarter)
	db.report.write(subreport_header(f"Disposals in {quarter}", q))
	db.query_and_render(q)

	q = q_pnl(quarter)
	db.report.write(subreport_header(f"Profit and loss in {quarter}", q))
	db.query_and_render(q)

	q = q_acquisitions(quarter, currency_re)
	db.report.write(subreport_header(f"Acquisitions in {quarter}", q))
	db.query_and_render(q)

if __name__ == '__main__':
	ledger_path = sys.argv[1]   # "build/final.beancount"
	out_path = sys.argv[2]   # "build/report.txt"

	print(f"Generating report for beancount file {ledger_path} and writing to {out_path}")
	db = ReportDriver(ledger_path, out_path)

	f = Figlet(width=120)
				
	for ty in range(2018, 2022 + 1):
		for quarter_n in [1, 2, 3, 4]:
			quarter_report(ty, quarter_n, db)
