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

#
# Queries
# TODO: parameterize the account names out of these queries
#

def inventory(date: str, currency_re: str):
	return (
		f'SELECT account, SUM(position) as lots, '
		f'UNITS(SUM(position)) AS total, COST(SUM(position)) AS total_cost '
		f'FROM has_account("Assets") CLOSE ON {date} '
		f'WHERE currency~"{currency_re}" ')

def disposals(quarter: str):
	return (
		f'SELECT date, narration, account, '
		f'units(position) as amount, '
		f'round(number(cost(position)) / number(units(position)), 4) as cost_each, '
		f'cost(position) as total_cost ' 
		f'FROM has_account("PnL") and quarter(date) = "{quarter}" ')

def acquisitions(quarter: str, currency_re: str):
	# This has query code in common with disposals(); consider refactoring.
	return (
		f'SELECT date, narration, account, '
		f'units(position) as amount, '
		f'round(number(cost(position)) / number(units(position)), 4) as cost_each, '
		f'cost(position) as total_cost ' 
		f'FROM quarter(date) = "{quarter}" '
		f'AND NOT has_account("Income:Mining") '
		f'WHERE number > 0 and currency~"{currency_re}" ')

def mining_summary(quarter: str, currency_re: str):
	return (
		f'SELECT units(sum(position)) '
		f'FROM quarter(date) = "{quarter}" AND has_account("Income:Mining")')

def mining_full(quarter: str, currency_re: str):
	# This has query code in common with disposals(); consider refactoring.
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

def pnl(quarter: str):
	return (
		f'SELECT date, narration, account, cost(position) as amount, balance '
		f'FROM has_account("PnL") AND quarter(date) = "{quarter}" '
		f'WHERE account="Income:PnL"')

def year_large_disposals(year: int):
	# TODO: cost(position) is the same as number.  Is this right?  Is it what we want to report?
	return (
		f'SELECT date, narration, account, cost(position) as amount, balance '
		f'FROM has_account("PnL") AND year(date) = {year} '
		f'WHERE account="Income:PnL" '
		f'AND abs(number) >= 1000')
		
def year_small_disposals(year: int):
	# TODO: cost(position) is the same as number.  Is this right?  Is it what we want to report?
	return (
		f'SELECT account, count(*) as num_transactions, '
		f'sum(cost(position)) as total '
		f'FROM has_account("PnL") AND year(date) = {year} '
		f'WHERE account="Income:PnL" AND abs(number) < 1000')

def year_mining_income_by_quarter(year: int):
	return (
		f'SELECT units(sum(position)) as total, '
		f'quarter(date) as quarter from year(date) = {year} '
		f'AND has_account("Income:Mining") GROUP BY quarter')

def year_mining_income_total(year: int):
	return (
		f'SELECT units(sum(position)) as total '
		f'FROM year(date) = {year} '
		f'AND has_account("Income:Mining") '
		f'WHERE currency="USD"')