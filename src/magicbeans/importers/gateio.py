"""Importer for csv's of processed data from GateIO, currently hard-coded
   to handle USD, USDT, and XCH.
"""
__copyright__ = "Copyright (C) 2023  Eric Altendorf"
__license__ = "GNU GPLv2"

from collections import defaultdict
import csv
import datetime
from decimal import Decimal
import decimal
from typing import NamedTuple
import re
import sys

from os import path
from magicbeans import common
from magicbeans.config import Config
from magicbeans.transfers import Link, Network
from magicbeans.tripod import Tripod
from beancount.core.data import Posting
from beancount.core.position import Cost
from dateutil.parser import parse
import pytz

from beancount.core import account
from beancount.core import amount
from beancount.core import data
from beancount.core import flags
from beancount.core import position
from beancount.core.number import D
from beancount.core.number import ZERO

import beangulp
from beangulp.testing import main

gateio_headers = 'no,time,action_desc,action_data,type,change_amount,amount,total'
inreader = csv.DictReader(sys.stdin, delimiter=',', quotechar='"')

# The timezone that the Gate.io CSV dumper (implicitly) assumed and
# rendered into.  We'll interpret timestamps as being in this timezone
# then convert them to UTC timestamps.
rendered_tz = 'Asia/Singapore'   # 'US/Pacific'

def CheckOrSet(d, k, v):
    if k in d:
        if d[k] != v:
            raise Exception(f"Can't set {k}={v}; key already set to {d[k]}")
    else:
        d[k] = v

def DecDict():
    return defaultdict(lambda: decimal.Decimal(0))
def StrDict():
    return defaultdict(lambda: '')

# TODO: rename to imputed?  And/or look at using tripod.py

def rcvd_cost(rcvd_cur: str, sent_cur: str, tx_ts: datetime, config: Config):
    """Compute cost basis per item recieved, if appropriate"""
    
    # We didn't send anything to get this, so it was a transfer in; no cost basis.
    if not sent_cur:
        return None

    elif rcvd_cur in ["XCH", "USDT"]:
        cost = config.get_price_fetcher().get_price(rcvd_cur, tx_ts)
        return Cost(cost, "USD", None, None)

    else:
        raise Exception(f"Unknown currency {rcvd_cur}")

def sent_price(rcvd_cur: str, sent_cur: str, tx_ts: datetime, config: Config):
    """Compute price for items disposed of, if appropriate"""

    # If we sent something but didn't recieve anything, it was a transfer not a disposal.
    if not rcvd_cur:
        return None

    elif sent_cur in ["XCH", "USDT"]:
        price = config.get_price_fetcher().get_price(sent_cur, tx_ts)
        return amount.Amount(price, "USD")

    else:
        raise Exception(f"Unknown currency {sent_cur}")

class GateIOImporter(beangulp.Importer):
    """An importer for GateIO csv files."""

    def __init__(self, account_root, account_pnl, account_fees, config: Config):
        self.account_root = account_root
        self.account_pnl = account_pnl
        self.account_fees = account_fees
        self.config = config

    def name(self) -> str:
        return 'GateIO'

    def identify(self, filepath):
        filename_re = r"^joined.csv$"
        if not re.match(filename_re, path.basename(filepath)):
            return False
        
        if not common.file_begins_with(filepath, gateio_headers):
            return False
            
        return True

    def filename(self, filepath):
        return "gateio.{}".format(path.basename(filepath))

    def account(self, filepath):
        return self.account_root

    def extract(self, filepath, existing):
        # Might be worth pulling this out into tripod.py as a Tripod-set builder.
        order_ids = set()
        rcvd_amt = DecDict()
        rcvd_cur = StrDict()
        sent_amt = DecDict()
        sent_cur = StrDict()
        fees_amt = DecDict()
        fees_cur = StrDict()

        # TODO: what were these for?  they're populated but never used.
        ext_amt = DecDict()
        ext_cur = StrDict()

        # TODO: this doesn't appear to be used anymore either (populated but not used)
        label = StrDict()

        tx_ts_min = {}  # Transaction timestamp range
        tx_ts_max = {}
        metadata_dict = {}

        entries = []
        with open(filepath) as infile:
            # Phase one: accumulate amounts on order IDs
            for index, row in enumerate(csv.DictReader(infile)):
                # Order ID identifies the user-initiated action that led to the
                # transactions in order execution.
                oid = row['action_data']
                order_ids.add(oid)

                meta = data.new_metadata(filepath, index)
                if oid not in metadata_dict:
                    metadata_dict[oid] = meta

                # Translate timestamps and record timestamp windows
                naive_dt = datetime.datetime.strptime(row['time'], '%Y-%m-%d %H:%M:%S')
                local_dt = pytz.timezone(rendered_tz).localize(naive_dt)
                utc_dt = local_dt.astimezone(pytz.timezone('UTC'))
                if not oid in tx_ts_min or tx_ts_min[oid] > utc_dt:
                    tx_ts_min[oid] = utc_dt
                if not oid in tx_ts_max or tx_ts_max[oid] < utc_dt:
                    tx_ts_max[oid] = utc_dt

                # Get the currency and amount
                ch_amt = decimal.Decimal(row['change_amount'])
                currency = row['type']
                assert currency in ["XCH", "USDT"]
                
                # Note: The CSV also contains 'amount' and 'total'.  In theory
                # these could be used for creating balance directives, but they
                # are fairly difficult to interpret automatically.  It's not
                # clear what exactly they represent, or how/when they differ
                # from each other; the only one we can use for a balance
                # directive is the final one of the group, but they're not
                # always ordered, and we could only use it when there's enough
                # of a break between transactions that we can clearly insert a
                # balance directive at the right point given Beancount's lack of
                # sub-day resolution timestamps.

                # Now process 
                action = row['action_desc']
                if action == 'Order Placed':
                    CheckOrSet(sent_cur, oid, currency)
                    sent_amt[oid] -= ch_amt
                    if currency == "USDT":
                        CheckOrSet(label, oid, "Buy (from USDT)")

                elif action == 'Order Fullfilled':
                    CheckOrSet(rcvd_cur, oid, currency)
                    rcvd_amt[oid] += ch_amt
                    if currency == "USDT":
                        CheckOrSet(label, oid, "Sell (to USDT)")

                elif action == 'Trade Fee':
                    CheckOrSet(fees_cur, oid, currency)
                    fees_amt[oid] -= ch_amt  # Fees are neg. in input

                elif action == 'Deposit':
                    # Actually shouldn't be in any of the dicts
                    assert not oid in rcvd_amt
                    rcvd_amt[oid] = ch_amt
                    rcvd_cur[oid] = currency
                    ext_amt[oid] = -ch_amt     # TODO: this is never used!
                    ext_cur[oid] = currency     # TODO: this is never used!
                    label[oid] = "Deposit"

                elif action == 'Withdraw':
                    # Actually shouldn't be in any of the dicts
                    assert not oid in sent_amt
                    sent_amt[oid] = -ch_amt
                    sent_cur[oid] = currency
                    ext_amt[oid] = -ch_amt     # TODO: this is never used!
                    ext_cur[oid] = currency     # TODO: this is never used!
                    label[oid] = "Withdraw"

                else:
                    assert False, f"Unknown action {action}"

            # Phase 2: process totals for each order ID
            for oid in sorted(order_ids, key=tx_ts_min.get):
                timestamp = tx_ts_min[oid]
                date = timestamp.date()
                meta = metadata_dict[oid]

                tripod = Tripod(rcvd_amt=rcvd_amt[oid],
                                rcvd_cur=rcvd_cur[oid],
                                sent_amt=sent_amt[oid],
                                sent_cur=sent_cur[oid],
                                fees_amt=fees_amt[oid],
                                fees_cur=fees_cur[oid])
                
                desc = f'{tripod.narrate()} tx:{oid}'
                links = set()

                postings = []
                if tripod.is_transfer():
                    local_acct = account.join(self.account_root, tripod.xfer_cur())
                    remote_acct = self.config.get_network().route(
                        tripod.is_send(), local_acct, tripod.xfer_cur())
                    xfer_amt = amount.Amount(tripod.xfer_amt(), tripod.xfer_cur())
                    xfer_amt_neg = amount.Amount(-tripod.xfer_amt(), tripod.xfer_cur())
                    xfer_cost = common.usd_cost_spec(tripod.xfer_cur())

                    # Attach cost basis to the neg outgoing leg.
                    # TODO: or to both???
                    if tripod.is_receive():
                        postings.append(
                            Posting(local_acct, xfer_amt, xfer_cost, None, None, None))
                        postings.append(
                            Posting(remote_acct, xfer_amt_neg, xfer_cost, None, None, None))
                    elif tripod.is_send():
                        postings.append(
                            Posting(local_acct, xfer_amt_neg, xfer_cost, None, None, None))
                        postings.append(
                            Posting(remote_acct, xfer_amt, xfer_cost, None, None, None))

                elif tripod.is_transaction():
                    credit_acct = account.join(self.account_root, tripod.rcvd_cur)
                    debit_acct = account.join(self.account_root, tripod.sent_cur)

                    postings.append(
                        Posting(credit_acct, 
                                amount.Amount(tripod.rcvd_amt, tripod.rcvd_cur),
                                rcvd_cost(rcvd_cur[oid], sent_cur[oid], timestamp, self.config),
                                None, None, None))
                    postings.append(
                        Posting(debit_acct,
                                amount.Amount(-tripod.sent_amt, tripod.sent_cur),
                                Cost(None, None, None, None),
                                sent_price(rcvd_cur[oid], sent_cur[oid], timestamp, self.config),
                                None, None))

                else:
                    assert False, "Unexpected tripod type"

                # We'll set this to true if we dispose of an asset, either by a
                # sale or an implicit sale by paying fees in non-USD.
                has_disposal = False

                # Gate.io charges fees in crypto.  So what we need to do is take
                # the crypto fee amount, book it as a "sale" at current FMV, and
                # the book a fee expense for that amount of USD.  We attach
                # metadata to mark these transactions because as a workaround
                # for now we need to split them out (see below).
                if tripod.fees_amt:
                    if tripod.fees_cur == "USD":
                        raise Exception("not expecting USD feeds in GateIO")

                    # Price to use for the virtual exchange
                    fee_cur_price = self.config.get_price_fetcher().get_price(tripod.fees_cur, timestamp)
                    fees_in_usd = tripod.fees_amt * fee_cur_price

                    # Book the sale
                    postings.append(
                        Posting(account.join(self.account_root, tripod.fees_cur),
                                amount.Amount(-fees_amt[oid], tripod.fees_cur),
                                Cost(None, None, None, None),
                                amount.Amount(fee_cur_price, "USD"),
                                None, {'is_fee': True}))

                    # Book the fee
                    postings.append(
                        Posting(self.account_fees,   #account.join(self.account_fees, "USD"),
                                amount.Amount(fees_in_usd, "USD"),
                                None,
                                None,
                                None, {'is_fee': True}))

                    # "sale" of the asset may accrue PnL
                    postings.append(
                        Posting(self.account_pnl, None, None, None, None, {'is_fee': True}))

                # PnL
                if tripod.is_transaction():
                    if tripod.sent_cur == "USD":
                        raise Exception("not expecting USD disposals in GateIO")
                    postings.append(
                        Posting(self.account_pnl, None, None, None, None, None))

                tx = data.Transaction(meta, date, flags.FLAG_OKAY,
                                      None, desc, data.EMPTY_SET, links,
                                      postings)
                common.attach_timestamp(tx, timestamp)

                # Because this may be a "sale" of an asset also purchased in the
                # same transaction, and this breaks beancount accounting, as a
                # workaround we currently split out the fees as a separate
                # transaction that happens immediately after the primary
                # transaction.
                (reg_tx, fee_tx) = common.split_out_marked_fees(tx, self.account_pnl)
                if reg_tx and fee_tx:
                    entries.append(reg_tx)
                    entries.append(fee_tx)
                else:
                    entries.append(tx)

        return entries