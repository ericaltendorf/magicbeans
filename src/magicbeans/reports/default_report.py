import datetime
from decimal import Decimal
from typing import List
from tabulate import tabulate

from beanquery.query import run_query
from beanquery.query_render import render_text
from magicbeans import queries
from magicbeans.reports import driver

#
# Default report generator.  Creates a report with
# a cover page, tax year summaries, and detailed disposals reports.
#

def generate(tax_years: List[int], numeraire: str, currencies: List[str], ledger_path: str, out_path: str):
	print(f"Generating report for beancount file {ledger_path} "
          f"and writing to {out_path}")

	db = driver.ReportDriver(ledger_path, out_path, numeraire)

	db.coverpage(datetime.datetime.now(), tax_years, currencies)

	print()
	db.renderer.newpage()

	print("Generating tax liability reports:")
	db.renderer.header("Capital Gains/Loss Tax Liability Estimates")

	# Federal plus California.  TODO: Configure
	fed_st_rate = Decimal("0.37")
	fed_lt_rate = Decimal("0.20")
	state_rate = Decimal("0.133")
	db.renderer.write_paragraph(f"""
		The following are rough estimates of the capital gains tax liability (or 
		credit, shown as negative values, in the case of losses) for each year. 
		These estimates are simple multiplications of the gain/loss by the tax 
		rate, using a marginal federal short-term capital gains tax rate of 
		{fed_st_rate:.0%} and long-term rate of {fed_lt_rate:.0%}, and a state 
		rate of {state_rate:.1%}.""".replace("%", "\%"))

	for ty in tax_years:
		print(f"  {ty}", end="", flush=True)
		db.renderer.subheader(f"{ty} Gain/Loss and Est. Tax Liability")
		db.run_tax_estimate_report(ty, fed_st_rate + state_rate, fed_lt_rate + state_rate)

	print("Generating tax summaries:")
	for ty in tax_years:
		print(f"  {ty}", end="", flush=True)

		db.renderer.header(f"{ty} Tax Reporting Info")

		db.renderer.subheader(f"{ty} Disposals and Gain/Loss, Order-level (for 8949)")
		db.run_disposals_8949(ty, consolidate=True)

		db.run_mining_income_sched_c(f"{ty} Mining Income (for Sched. C)", ty)

	print()

	print("Generating detailed disposals reports:")
	for ty in tax_years:
		start = datetime.date(ty, 1, 1)
		end = datetime.date(ty+1, 1, 1)
		print(f"  {ty}", flush=True)
		db.run_detailed_log(start, end)

	print()

	db.close()