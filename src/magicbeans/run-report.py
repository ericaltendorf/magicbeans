from enum import Enum
import subprocess
from beancount.core.amount import Amount
from beanquery.query_render import render_text
from pyfiglet import Figlet
from beancount import loader

from beancount.parser import parser
from beanquery.query import run_query
from tabulate import tabulate

ledger = "build/final.beancount"
build_dir = "build"
report_txt = f"{build_dir}/report.txt"

class BeanDB:
	"""Simple wrapper around a beancount database facilitating bean-query queries"""

	def __init__(self, entries, options) -> None:
		self.entries = entries
		self.options = options
	
	def query(self, query: str):
		"""Run a bean-query query on the entries in this database.  Returns a
		list of (name, dtype) tuples describing the results set table and a list
		of ResultRow tuples with the data.item pairs."""
		return run_query(entries, options, query)

	def render(self, rtypes, rrows, out):
		render_text(rtypes, rrows, self.options['dcontext'], out,
	      			expand=True, boxed=False, narrow=False)

	def query_and_render(self, query: str, out):
		(rtypes, rrows) = self.query(query)
		self.render(rtypes, rrows, out)

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
		f'SELECT account, SUM(position) as Lots, '
		f'UNITS(SUM(position)) AS Total, COST(SUM(position)) AS TotalCost '
		f'FROM has_account("Assets") CLOSE ON {date} '
		f'WHERE currency~"{currency_re}" ')

def q_disposals(quarter: str):
	return (
		f'SELECT date, narration, account, cost(position), units(position) '
		f'FROM has_account("PnL") and quarter(date) = "{quarter}" ')

def q_pnl(quarter: str):
	return (
		f'SELECT date, narration, account, cost(position) as amount, balance '
		f'FROM has_account("PnL") AND quarter(date) = "{quarter}" '
		f'WHERE account="Income:PnL"')

#
# Report generation helpers
#

def subreport_header(title: str, q: str):
	return f"{title}\n\n{q}\n\n"

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

def quarter_report(year: int, quarter_n: int, db, out):
	quarter = f"{ty}-Q{quarter_n}"
	quarter_begin = f"""{ty}-{["01", "04", "07", "10"][quarter_n-1]}-01"""

	out.write(f.renderText(f"{year} Q {quarter_n} : inventory"))

	q =	q_inventory(quarter_begin, "BTC|ETH|LTC|XCH")
	out.write(subreport_header(f"Inventory as of {quarter_begin}", q))
	db.query_and_render(q, out)
	out.write("\n")

	out.write(f.renderText(f"{year} Q {quarter_n} : disposals"))

	q = q_disposals(quarter)
	out.write(subreport_header(f"Disposals in {quarter}", q))
	db.query_and_render(q, out)
	out.write("\n")

	q = q_pnl(quarter)
	out.write(subreport_header(f"Profit and loss in {quarter}", q))
	db.query_and_render(q, out)
	out.write("\n")


if __name__ == '__main__':

	# entries, errors, options = parser.parse_file(ledger)
	entries, errors, options = loader.load_file(ledger)
	db = BeanDB(entries, options)

	with open(report_txt, 'w') as out:
		f = Figlet(width=120)
					
		for ty in range(2018, 2022 + 1):
			for quarter_n in [1, 2, 3, 4]:
				quarter_report(ty, quarter_n, db, out)
