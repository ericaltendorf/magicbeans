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
		db.run_tax_reporting_summary(ty)

	print()

	# db.renderer.header("Quarterly Operations")
	# print("Generating quarterly operations reports:")
	# for ty in tax_years:
	# 	print(f"  {ty} ", end="", flush=True)
	# 	for q in [1, 2, 3, 4]:
	# 		print(f"{q} ", end="", flush=True)
	# 		start = quarter_start(ty, q)
	# 		db.renderer.header(f"{ty} Q {q}")
	# 		db.disposals(quarter_start(ty, q), quarter_end(ty, q), True)

	print("Generating detailed disposals reports:")
	for ty in tax_years:
		start = datetime.date(ty, 1, 1)
		end = datetime.date(ty+1, 1, 1)
		print(f"  {ty}", flush=True)
		db.run_detailed_log(start, end)

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