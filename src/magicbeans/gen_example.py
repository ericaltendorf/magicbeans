import datetime
from decimal import Decimal
import decimal
import math
import random
import sys
import textwrap
from beancount.core import account, amount, flags
from beancount.core import data
from beancount.core.data import Posting, Transaction, create_simple_posting
from beancount.core.position import Cost
from beancount.parser import printer, parser
from magicbeans import mining, prices
from magicbeans.reports import default_report
import pytz

# N.b.: There are a few places here where it would feel natural to use set()
# objects.  However, sets introduce nondeterminism, resulting in different 
# outputs from different runs even when the random seed is the same.  Thus,
# we use lists throughout.

# TODO:
#   Model fees
#   Add more interesting narrations

START_YEAR = 2020
END_YEAR = 2023   # Exclusive
ACCT_PREFIX = "Assets:Account"
CURRENCIES = [ 'USD', 'USDT', 'BTC', 'ETH', 'XCH' ]
MIN_BALANCE = { 'USDT': Decimal('1000.00'),   # Don't sell low balances
                'BTC': Decimal('0.1'),
                'ETH': Decimal('2.0'),
                'XCH': Decimal('8.0')}
BASE_CURS = [ 'USD', 'USDT' ]
SIZES = [ 100, 500, 1000, 1500, 2000, 2500, 5000, 10000, 15000, 20000,
          25000, 30000, 35000, 40000, 45000, 50000, 60000, 80000 ]
GAPS = [ 1, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 5, 7, 10, 14, 19, 25, 33 ]

def sd_round(amount: Decimal, sd: int):
    '''Round to sd significant digits.'''
    with decimal.localcontext() as ctx:
        ctx.rounding = decimal.ROUND_DOWN
        num_digits = 0 if amount == 0 else math.ceil(math.log10(amount))
        return round(amount, sd - num_digits)

def parse(input_string):
    entries, errors, options_map = parser.parse_string(textwrap.dedent(input_string))
    if errors:
        printer.print_errors(errors, file=sys.stderr)
        raise ValueError("Parsed text has errors")
    return data.sorted(entries)

def mk_tx(date, sent_cur, sent_amt, sent_price, rcvd_cur, rcvd_amt, rcvd_price, fees_cur, fees_amt):
    '''Construct a beancount Transaction given the parameters.'''
    rcvd_acct = f"{ACCT_PREFIX}:{rcvd_cur}"
    if sent_cur == "USD":
        narration = f"Buy {rcvd_amt:.4f} {rcvd_cur} with {sent_amt:.4f} {sent_cur}"
    elif rcvd_cur == "USD":
        narration = f"Sell {sent_amt:.4f} {sent_cur} for {rcvd_amt:.4f} {rcvd_cur}"
    elif sent_cur == "":
        narration = f"Mining reward of {rcvd_amt:.4f} {rcvd_cur}"
        rcvd_acct = mining.MINING_BENEFICIARY_ACCOUNT
    else:
        narration = f"Exchange {sent_amt:.4f} {sent_cur} for {rcvd_amt:.4f} {rcvd_cur}"

    postings = []
    postings.append(
        Posting(rcvd_acct,
                amount.Amount(rcvd_amt, rcvd_cur),
                None if rcvd_cur == "USD" else Cost(rcvd_price, "USD", None, None),
                None,
                None, None))
    if sent_cur != "":
        postings.append(
            Posting(f"{ACCT_PREFIX}:{sent_cur}",
                    amount.Amount(-sent_amt, sent_cur),
                    None if sent_cur == "USD" else Cost(None, None, None, None),
                    amount.Amount(sent_price, "USD"),
                    None, None))
        if sent_cur != "USD":
            postings.append(Posting("Income:CapGains", None, None, None, None, None))
    else:
        postings.append(Posting(mining.MINING_INCOME_ACCOUNT, None, None, None, None, None))

    return data.Transaction({}, date, flags.FLAG_OKAY, None,
                            narration, data.EMPTY_SET, data.EMPTY_SET, postings)
    
def random_time(date: datetime.date):
    return datetime.datetime.combine(
        date,
        datetime.time(hour=random.randint(0, 23),
                      minute=random.randint(0, 59),
                      second=random.randint(0, 59)),
        tzinfo=pytz.utc)

def rcvd_cur_choices(date: datetime.date, sent_cur: str):
    initial_choices = CURRENCIES if sent_cur in BASE_CURS else BASE_CURS
    disallowed = [sent_cur]
    if date < datetime.date(2021, 7, 1):
        disallowed.append("XCH")
    return [t for t in initial_choices if t not in disallowed]

def random_trade(date: datetime.date, balances: dict, price_fetcher):
    '''Randomly generate a trade.'''

    timestamp = random_time(date)

    numeraire = "USD"
    sufficient_curs = [c for c in balances.keys() if balances[c] > MIN_BALANCE.get(c, 0)]
    sent_cur = random.choice([numeraire] + sufficient_curs)
    rcvd_cur = random.choice(list(rcvd_cur_choices(date, sent_cur)))

    rcvd_price = (Decimal('1.0') if rcvd_cur == numeraire else
        price_fetcher.get_price(rcvd_cur, timestamp))
    sent_price = (Decimal('1.0') if sent_cur == numeraire else
        price_fetcher.get_price(sent_cur, timestamp))

    max_usd_trade_size = balances[sent_cur] * sent_price
    approx_usd_trade_size = random.choice([s for s in SIZES if s < max_usd_trade_size])

    # Trade in approx even amounts of tokens, rather than even amounts of USD
    if sent_cur in BASE_CURS:
        rcvd_amt = sd_round(approx_usd_trade_size / rcvd_price, 2)
        sent_amt = rcvd_amt * rcvd_price / sent_price
    else:
        sent_amt = sd_round(approx_usd_trade_size / sent_price, 2)
        rcvd_amt = sent_amt * sent_price / rcvd_price

    # TODO
    fees_cur = sent_cur
    fees_amt = Decimal('0')

    balances[rcvd_cur] = balances.get(rcvd_cur, Decimal('0')) + rcvd_amt
    balances[sent_cur] = balances.get(sent_cur, Decimal('0')) - sent_amt

    return mk_tx(date, sent_cur, sent_amt, sent_price, rcvd_cur, rcvd_amt, rcvd_price, fees_cur, fees_amt)

if __name__ == '__main__':
    start_date = datetime.date(START_YEAR, 1, 1)
    end_date = datetime.date(END_YEAR, 1, 1)
    balances = {"USD": Decimal('1000000.00')}  # Start with $1MM
    entries = []

    # These paths are hardcoded, so you need to run from the git root.
    beancount_path = "data/magicbeans_example.beancount"
    report_path = "data/magicbeans_example"  # .pdf

    # Be repeatable.
    random.seed(0)

    # Preambles
    OPTIONS = textwrap.dedent("""
        ;; -*- mode: beancount; -*-
        ;; Fake transactions for example report generation

        option "title" "Crypto Trading"
        option "operating_currency" "USD"
        option "booking_method" "HIFO"
        option "inferred_tolerance_default" "USD:0.01"

        plugin "beancount_reds_plugins.capital_gains_classifier.long_short" "{
        'Income.*:CapGains': [':CapGains', ':CapGains:Short', ':CapGains:Long']
        }"
        """)
    accounts = (["Income:CapGains", mining.MINING_INCOME_ACCOUNT, mining.MINING_BENEFICIARY_ACCOUNT] +
        [f"{ACCT_PREFIX}:{token}" for token in CURRENCIES])
    for account in accounts:
        entries.append(parse(f"2020-01-01 open {account}")[0])

    # Transactions: mostly trades, occasionally insert a mining reward.
    price_fetcher = prices.PriceFetcher(prices.Resolution.DAY, "data/prices.csv")
    day = start_date
    while day < end_date:
        tx = random_trade(day, balances, price_fetcher)
        entries.append(tx)

        gap = random.choice(GAPS)

        if gap > 3 and day > datetime.date(2021, 7, 1):
            reward_day = day + datetime.timedelta(days=2)
            if reward_day < end_date:
                reward_ts = random_time(reward_day)
                reward_cur = "XCH"  # TODO: mining is a bit hardcoded to XCH right now
                price = price_fetcher.get_price(reward_cur, reward_ts)
                reward_amt = sd_round(Decimal(random.uniform(float(Decimal(100) / price),
                                                            float(Decimal(200) / price))),
                                                            8)
                # Note: mining rewards accrue to mining.MINING_BENEFICIARY_ACCOUNT, and
                # this demo doesn't implement transfers, so these just accrue and are
                # never eligible for sale in the normal asset account.
                tx = mk_tx(reward_day, "", Decimal('0'), Decimal('0'),
                        reward_cur, reward_amt, price,
                        "", Decimal('0'))
                entries.append(tx)

        day += datetime.timedelta(days=gap)

    # Close up and save everything
    price_fetcher.write_cache_file()
    with open(beancount_path, 'w') as out:
        out.write(OPTIONS + "\n")
        parser.printer.print_entries(entries, file=out)

    # Now generate the report
    default_report.run(range(START_YEAR, END_YEAR), "USD", CURRENCIES,
                   beancount_path, report_path)