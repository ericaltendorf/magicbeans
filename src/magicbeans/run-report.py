# TODOS:
# - figure out how to issue `set expand true` to bean-query
# - Figure out how to generate PDFs.  The following generates large font text.
#   more research is needed to produce good pdfs
#       soffice --convert-to pdf $REPORT_TXT --outdir $BUILD_DIR

from enum import Enum
import subprocess
from pyfiglet import Figlet
from beancount import loader

from beancount.parser import parser
from beanquery.query import run_query
from tabulate import tabulate

ledger = "build/final.beancount"
build_dir = "build"
report_txt = f"{build_dir}/report.txt"

qheader = "=" * 140

#
# Helpers
#

class Format(Enum):
	TEXT = 1
	HTML = 2
	PDF = 3

class BeanDB:
	def __init__(self, entries, options) -> None:
		self.entries = entries
		self.options = options
	
	def query(self, query: str):
		"""Run a bean-query query on the entries in this database.  Returns a
		list of (name, dtype) tuples describing the results set table and a list
		of ResultRow tuples with the data.item pairs."""
		return run_query(entries, options, query)

	def report(self, query: str, format: Format = Format.TEXT):
		"""Run a bean-query query on the entries in this database.  Returns a
		string containing the report in the requested format."""
		(rtypes, rrows) = self.query(query)
		if len(rrows) == 0:
			return ""

		if format == Format.TEXT:
			return tabulate(rrows, headers=[r.name for r in rtypes],
		   					tablefmt="simple", maxcolwidths=80)


def run_query_subproc(query: str):
	"""Probably obsolete"""
	proc = subprocess.run(["bean-query", ledger, query],
		       check=True, capture_output=True)	
	return proc.stdout.decode('utf-8')

def group_rows_by_id(rows):
	"""Given a table in ascii format, one line per table row, with two header
	rows, and assuming the first column is a 32-character id, and the second is
	a date, return the table with the ids removed and the date for followon rows
	replaced with blank spaces."""
	rows = rows.split("\n")
	result = []
	last_id = None
	for (i, row) in enumerate(rows):
		if i < 2:
			result.append(row[34:])
		else:
			if row[:32] != last_id:
				if last_id is not None:
					result.append("")
				result.append(row[34:])
				last_id = row[:32]
			else:
				result.append(" " * 12 + row[46:])

	return "\n".join(result) + "\n"

def format_subreport(title: str, q: str, report: str):
	return f"{qheader}\n"\
		f"{title}\n\n"\
		f"{q}\n\n"\
		f"{report}\n\n"

def quarter_starts(year: int):
	return [f"{year}-01-01", f"{year}-04-01", f"{year}-07-01", f"{year}-10-01"]

def periods(dates):
	for i in range(len(dates) - 1):
		yield (dates[i], dates[i+1])

#
# Queries
#

def q_fees(ty: int):
	return f"""SELECT account, sum(position)
	FROM has_account("Fees") OPEN ON {ty}-01-01 CLOSE ON {ty+1}-01-01
	WHERE account ~ "Fees" """

def q_inventory(date: str, currency: str):
	return f"""SELECT account, SUM(position) as lots
	FROM has_account("Assets") CLOSE ON {date}
	WHERE currency="{currency}" """

def q_disposals_start_end(date_start: str, date_end: str):
	return f"""SELECT id, date, account, narration, cost(position), units(position)
	FROM has_account("PnL") and {date_start} < date and date < {date_end}"""

def q_disposals(quarter: str):
	return f"""SELECT id, date, account, narration, cost(position), units(position)
	FROM has_account("PnL") and quarter(date) = "{quarter}" """

if __name__ == '__main__':

	# entries, errors, options = parser.parse_file(ledger)
	entries, errors, options = loader.load_file(ledger)
	db = BeanDB(entries, options)

	with open(report_txt, 'w') as out:
		# for ty in [2018, 2019, 2020]:
		# 	q = q_fees(ty)
		# 	# fee_report = db.report(q)  # switch to this when bean-query is fixed
		# 	fee_report = run_query_subproc(q)
		# 	out.write(format_subreport(f"Fees {ty}", q, fee_report))

		# for currency in ["BTC"]: #["BTC", "ETH", "LTC", "XCH"]:
		# 	for ty in [2018, 2019, 2020]:
		# 		for date in quarter_starts(ty):
		# 			q = q_inventory(date, currency)
		# 			usd_report = run_query_subproc(q)
		# 			out.write(format_subreport(f"{currency} Inventory {date}", q, usd_report))
		f = Figlet(width=120)
					
		for ty in ["2020"]:
			for quarter_n in [1, 2, 3, 4]:
				quarter = f"{ty}-Q{quarter_n}"
				quarter_begin = f"""{ty}-{["01", "04", "07", "10"][quarter_n-1]}-01"""

				out.write(f.renderText(f"{quarter} : inventories"))

				for currency in ["BTC", "ETH", "LTC", "XCH"]:
					q =	q_inventory(quarter_begin, currency)
					report = db.report(q)
					out.write(format_subreport(f"{currency} Inventory {quarter_begin}", q, report))

				out.write(f.renderText(f"{quarter} : disposals"))

				q = q_disposals(quarter)
				report = db.report(q)
				out.write(format_subreport(f"Disposals {quarter}", q, report))

