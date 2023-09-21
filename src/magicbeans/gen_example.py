import datetime
from decimal import Decimal
import decimal
import math
import random
import sys
import textwrap
from beancount.core import account
from beancount.core import data
from beancount.core.data import Posting, Transaction, create_simple_posting
from beancount.parser import printer, parser
from magicbeans import prices, run_report
import pytz

# TODO: Model fees.

START_YEAR = 2020
END_YEAR = 2023   # Exclusive
ACCT_PREFIX = "Assets:Account"
TOKENS = [ 'BTC', 'ETH', 'XCH' ]
SIZES = [ 1000, 1500, 2000, 2500, 5000, 10000, 15000, 20000, 25000,
          30000, 35000, 40000, 45000, 50000, 60000, 80000, 100000 ]
GAPS = [ 1, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 5, 7, 10, 14, 19, 25, 33 ]

def sd_round(amount: Decimal, sd: int):
    '''Round to sd significant digits.'''
    with decimal.localcontext() as ctx:
        ctx.rounding = decimal.ROUND_DOWN
        num_digits = math.ceil(math.log10(amount))
        return round(amount, sd - num_digits)

def parse(input_string):
    entries, errors, options_map = parser.parse_string(textwrap.dedent(input_string))
    if errors:
        printer.print_errors(errors, file=sys.stderr)
        raise ValueError("Parsed text has errors")
    return data.sorted(entries)

def mk_tx(date, is_buy, token, amount, price):
    '''Construct a beancount Transaction given the parameters.'''
    amount_cash = amount * price
    if is_buy:
        return parse(f"""
            {date} * "Buy {token}"
              {ACCT_PREFIX}:{token}    {amount:.8f} {token} {{{price:.6f} USD}}
              {ACCT_PREFIX}:Cash       {-amount_cash:.4f} USD
        """)[0]
    else:
        return parse(f"""
            {date} * "Sell {token}"
              {ACCT_PREFIX}:{token}    {-amount:.8f} {token} {{}} @ {price:.6f} USD
              {ACCT_PREFIX}:Cash       {amount_cash:.4f} USD
              Income:CapGains
        """)[0]

def pick_token(date: datetime.date):
    token = random.choice(TOKENS)
    if token == 'XCH' and date < datetime.date(2021, 7, 1):
        token = 'BTC'
    return token

# TODO: generate USDT exchanges too
def random_tx(date: datetime.date, balances: dict, price_fetcher):
    '''Randomly generate either a buy or sell for a random token.'''
    # Can't sell if we don't have any tokens
    is_buy = (len(balances) == 0) or (random.random() < 0.6)
    if is_buy:
        token = pick_token(date)
    elif balances:
        token = random.choice(list(balances.keys()))

    # Pick random time of day...probably a more concise way to do this
    timestamp = datetime.datetime.combine(
        date,
        datetime.time(hour=random.randint(0, 23),
                      minute=random.randint(0, 59),
                      second=random.randint(0, 59)),
        tzinfo=pytz.utc)
    price = price_fetcher.get_price(token, timestamp)

    if is_buy:
        approx_usd_amount = random.choice(SIZES)
        token_amount = sd_round(approx_usd_amount / price, 2)
    else:
        token_amount = sd_round(decimal.Decimal(random.uniform(0.001, math.floor(balances[token]))), 2)

    balances[token] = balances.get(token, 0) + (token_amount if is_buy else -token_amount)

    return mk_tx(date, is_buy, token, token_amount, price)

if __name__ == '__main__':
    start_date = datetime.date(START_YEAR, 1, 1)
    end_date = datetime.date(END_YEAR, 1, 1)
    balances = {}
    entries = []
    beancount_path = "data/magicbeans_example.beancount"
    report_path = "data/magicbeans_example"  # .pdf

    # Be deterministic for any particular time period
    random.seed(f"{start_date}-{end_date}")

    # Preambles
    OPTIONS = textwrap.dedent(""";; -*- mode: beancount; -*-
        ;; Fake transactions for example report generation

        option "title" "Crypto Trading"
        option "operating_currency" "USD"
        option "booking_method" "HIFO"
        option "inferred_tolerance_default" "USD:0.01"

        plugin "beancount_reds_plugins.capital_gains_classifier.long_short" "{
        'Income.*:CapGains': [':CapGains', ':CapGains:Short', ':CapGains:Long']
        }"
        """)
    accounts = (["Income:CapGains", f"{ACCT_PREFIX}:Cash"] +
        [f"{ACCT_PREFIX}:{token}" for token in TOKENS])
    for account in accounts:
        entries.append(parse(f"2020-01-01 open {account}")[0])

    # Transactions
    price_fetcher = prices.PriceFetcher(prices.Resolution.DAY, "data/prices.csv")
    day = start_date
    while day < end_date:
        tx = random_tx(day, balances, price_fetcher)
        day += datetime.timedelta(days=random.choice(GAPS))
        entries.append(tx)

    # Close up and save everything
    price_fetcher.write_cache_file()
    with open(beancount_path, 'w') as out:
        out.write(OPTIONS + "\n")
        parser.printer.print_entries(entries, file=out)

    # Now generate the report
    run_report.run(range(START_YEAR, END_YEAR), TOKENS,
                   beancount_path, report_path)