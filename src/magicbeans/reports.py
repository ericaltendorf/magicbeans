import subprocess
import sys
from enum import Enum
import textwrap
from typing import List
from magicbeans import disposals

from pyfiglet import Figlet
from tabulate import tabulate

from beancount import loader
from beancount.core.amount import Amount
from beancount.parser import parser
from beanquery.query import run_query
from beanquery.query_render import render_text


def beancount_quarter(ty: int, quarter_n: int):
	return f"{ty}-Q{quarter_n}"

# TODO: parameterize the width of this header, probably
# via an argument on ReportDriver.
def subreport_header(title: str, q: str = None):
	# TODO: move this into ReportDriver?
	result = " " + ("_" * 140) + f" \n|{title:_^140}|\n"
	if q:
		result += "\n".join(textwrap.wrap(q, width=140,
		      initial_indent="", subsequent_indent="  "))
	return  result

class ReportDriver:
	"""Wraps a beancount file and facilitates reporting with BQL queries.

	Initialize the driver with the path to the beancount file and the path to
	the output report file.  Then call the other methods to run queries and
	write the results to the report file.
	"""	

	# TODO: query(), render(), and query_and_render() may be obsolete now.

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

	def run_subreport(self, title: str, query: str, footer: str = None):
		self.report.write(subreport_header(title, query))
		self.query_and_render(query, footer)

	def run_disposals_subreport(self, title: str, ty: int):
		self.report.write(subreport_header(title))
		ty_entries = [e for e in self.entries if e.date.year == ty]
		disposals.render_disposals_table(ty_entries, self.report)