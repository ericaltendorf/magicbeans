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


def beancount_quarter(ty: int, quarter_n: int):
	return f"{ty}-Q{quarter_n}"

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

	def run_subreport(self, title: str, query: str, footer: str = None):
		self.report.write(subreport_header(title, query))
		self.query_and_render(query, footer)

#
# Report generation helpers
#

def subreport_header(title: str, q: str):
	# TODO: move this into ReportDriver?
	return " " + ("_" * 98) + f" \n|{title:_^98}|\n\n{q}\n\n"