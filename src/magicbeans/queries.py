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
		f'SELECT date, '
		f'maxwidth(narration, 50) as narration, '
		f'account, '
		f'units(position) as amount, '
		f'round(number(cost(position)) / number(units(position)), 4) as cost_ea, '
		f'cost(position) as total_cost ' 
		f'FROM has_account("CapGains") and quarter(date) = "{quarter}" ')

def acquisitions(quarter: str, currency_re: str):
	# This has query code in common with disposals(); consider refactoring.
	return (
		f'SELECT date, '
		f'maxwidth(narration, 50) as narration, '
		f'account, '
		f'units(position) as amount, '
		f'round(number(cost(position)) / number(units(position)), 4) as cost_ea, '
		f'cost(position) as total_cost ' 
		f'FROM quarter(date) = "{quarter}" '
		# f'AND NOT has_account("Income:Mining") '  # This leg gets dropped from zero-cost mining rewards 
		f'AND NOT narration~"Mining reward" '       # so we need this hack instead....
		f'WHERE number > 0 and currency~"{currency_re}" ')

def mining_summary(quarter: str, currency_re: str):
	return (
		f'SELECT units(sum(position)) '
		f'FROM quarter(date) = "{quarter}" AND has_account("Income:Mining")')

def mining_full(quarter: str, currency_re: str):
	# This has query code in common with disposals(); consider refactoring.
	return (
		f'SELECT entry_meta("timestamp") as timestamp_utc, narration, '
		f'units(position) as amount, '
		f'units(sum(balance)) as run_total, '
		f'round(number(cost(position)) / number(units(position)), 4) as cost_ea, '
		f'cost(position) as cost, ' 
		f'cost(sum(balance)) as run_total_cost ' 
		f'FROM quarter(date) = "{quarter}" '
		# f'AND has_account("Income:Mining") '  # This leg gets dropped from zero-cost mining rewards 
		f'AND narration~"Mining reward" '   # so we need this hack instead....
		f'WHERE number > 0 and currency~"{currency_re}" ')

def pnl(quarter: str):
	return (
		f'SELECT date, narration, account, cost(position) as amount, balance '
		f'FROM quarter(date) = "{quarter}" '
		f'WHERE account~"Income:CapGains"')

def year_large_disposals(year: int):
	# TODO: cost(position) is the same as number.  Is this right?  Is it what we want to report?
	return (
		f'SELECT date, narration, account, round(cost(position),2) as amount, balance '
		f'FROM year(date) = {year} '
		f'WHERE account~"Income:CapGains" '
		f'AND abs(number) >= 1000')
		
def year_small_disposals(year: int):
	# TODO: cost(position) is the same as number.  Is this right?  Is it what we want to report?
	return (
		f'SELECT account, count(*) as num_transactions, '
		f'sum(cost(position)) as total '
		f'FROM year(date) = {year} '
		f'WHERE account~"Income:CapGains" AND abs(number) < 1000')

# def year_mining_income_by_quarter(year: int):
# 	return (
# 		f'SELECT '
# 		f'quarter(date) as quarter, '
# 		f'units(sum(filter_currency(position, "USD"))) as usd_subtotal, '
# 		f'units(sum(filter_currency(position, "XCH"))) as xch_subtotal '
# 		f'from year(date) = {year} '
# 		f'AND has_account("Income:Mining") ORDER BY quarter')   # broken anyway

# def year_mining_income_total(year: int):
# 	return (
# 		f'SELECT units(sum(position)) as total '
# 		f'FROM year(date) = {year} '
# 		f'AND has_account("Income:Mining") '   #broken anyway
# 		f'WHERE currency="USD"')