"""Importer for csv's of processed data from GateIO, currently hard-coded
   to handle USD, USDT, and XCH.
"""
__copyright__ = "Copyright (C) 2023  Eric Altendorf"
__license__ = "GNU GPLv2"

# TODO: throughout, replace hardcoded checks against "USD" with calls
# to a function that determines if disposals of the asset are subject
# to capital gains.

from collections import defaultdict
import csv
import datetime
from decimal import Decimal
import decimal
from typing import NamedTuple
import re
import sys

from os import path
from bean_crypto_import import common
from bean_crypto_import.tripod import Tripod
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

from bean_crypto_import.common import usd_cost_spec
from bean_crypto_import.config import Config, gio_compute_remote_account

gateio_headers = 'no,time,action_desc,action_data,type,change_amount,amount,total'
inreader = csv.DictReader(sys.stdin, delimiter=',', quotechar='"')

# The timezone that the Gate.io CSV dumper (implicitly) assumed and
# rendered into.  We'll interpret timestamps as being in this timezone
# then convert them to UTC timestamps.
rendered_tz = 'Asia/Singapore'   # 'US/Pacific'

def CheckOrSet(d, k, v):
    if k in d:
        assert d[k] == v
    else:
        d[k] = v

def DecDict():
    return defaultdict(lambda: decimal.Decimal(0))
def StrDict():
    return defaultdict(lambda: '')

# TODO: rename to imputed?  And/or look at using tripod.py

def ComputeRcvdCost(rcvd_cur: str, rcvd_amt: Decimal, sent_cur: str, sent_amt: Decimal):
    """Compute cost basis per item recieved, if appropriate"""
    # TODO: Replace these price estimates and assumptions with a data feed

    # We bought XCH using USD or USDT, so we are establishing a cost basis.
    if rcvd_cur == "XCH" and (sent_cur == "USDT" or sent_cur == "USD"):
        xch_usd = Decimal(sent_amt / rcvd_amt)
        return Cost(xch_usd, "USD", None, None)

    # We sold XCH for USDT, and we assume cost basis of 1 USDT is 1.0 USD.
    elif (rcvd_cur == "USDT" and sent_cur == "XCH"):
        return Cost(Decimal("1.0"), "USD", None, None)
    
    # We didn't send anything to get this, so it was a transfer in; no cost basis.
    elif not sent_cur:
        return None
    
    else:
        assert False

def ComputeSentPrice(rcvd_cur: str, rcvd_amt: Decimal, sent_cur: str, sent_amt: Decimal):
    """Compute price for items disposed of, if appropriate"""
    # TODO: Replace these price estimates and assumptions with a data feed

    # Disposed of XCH to obtain USD or USDT; compute price.
    if sent_cur == "XCH" and (rcvd_cur == "USDT" or rcvd_cur == "USD"):
        xch_usd = Decimal(rcvd_amt / sent_amt)
        return amount.Amount(xch_usd, "USD")
    
    # If we sent something but didn't recieve anything, it was a transfer not a disposal.
    elif not rcvd_cur:
        return None
    
    # Disposed of USDT; price is always 1.0 USD.
    elif sent_cur == "USDT":
        return amount.Amount(Decimal("1.0"), "USD")
    
    else:
        assert False, f"rcvd {rcvd_cur} sent {sent_cur}"

class GateIOImporter(beangulp.Importer):
    """An importer for GateIO csv files."""

    def __init__(self, account_root, account_external_root,
                 account_pnl, account_fees):
        self.account_root = account_root
        self.account_external_root = account_external_root
        self.account_pnl = account_pnl
        self.account_fees = account_fees

    def name(self) -> str:
        return 'GateIO'

    def identify(self, filepath):
        filename_re = r"joined.csv"
        if not re.match(filename_re, path.basename(filepath)):
            return False
        
        with open(filepath, "r") as file:
            head = file.read(len(gateio_headers))
            if (head != gateio_headers):
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
        ext_amt = DecDict()
        ext_cur = StrDict()
        label = StrDict()
        tx_ts_min = {}  # Transaction timestamp range
        tx_ts_max = {}

        entries = []
        with open(filepath) as infile:
            # Phase one: accumulate amounts on order IDs
            for index, row in enumerate(csv.DictReader(infile)):
                meta = data.new_metadata(filepath, index)

                # Order ID identifies the user-initiated action that led to the
                # transactions in order execution.
                oid = row['action_data']
                order_ids.add(oid)

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

                # TODO: row also contains an 'amount' field which should be
                # a running total which could be used for balance directives.

                # Now process 
                action = row['action_desc']
                if action == 'Order Placed':
                    CheckOrSet(sent_cur, oid, currency)
                    sent_amt[oid] -= ch_amt

                    if currency == "USD":
                        CheckOrSet(label, oid, "Buy")
                    elif currency == "USDT":
                        # TODO: this might break if we trade USD-USDT
                        CheckOrSet(label, oid, "Buy (from USDT)")

                elif action == 'Order Fullfilled':
                    CheckOrSet(rcvd_cur, oid, currency)
                    rcvd_amt[oid] += ch_amt

                    if currency == "USD":
                        CheckOrSet(label, oid, "Sell")
                    elif currency == "USDT":
                        # TODO: this might break if we trade USD-USDT
                        CheckOrSet(label, oid, "Sell (to USDT)")

                elif action == 'Trade Fee':
                    CheckOrSet(fees_cur, oid, currency)
                    fees_amt[oid] -= ch_amt  # Fees are neg. in input

                elif action == 'Deposit':
                    # Actually shouldn't be in any of the dicts
                    assert not oid in rcvd_amt
                    rcvd_amt[oid] = ch_amt
                    rcvd_cur[oid] = currency
                    ext_amt[oid] = -ch_amt
                    ext_cur[oid] = currency
                    label[oid] = "Deposit"

                elif action == 'Withdraw':
                    # Actually shouldn't be in any of the dicts
                    assert not oid in sent_amt
                    sent_amt[oid] = -ch_amt
                    sent_cur[oid] = currency
                    ext_amt[oid] = -ch_amt
                    ext_cur[oid] = currency
                    label[oid] = "Withdraw"

                else:
                    assert False, f"Unknown action {action}"

            # Phase 2: process totals for each order ID
            for oid in sorted(order_ids, key=tx_ts_min.get):
                timestamp = tx_ts_min[oid]
                date = timestamp.date()

                tripod = Tripod(rcvd_amt=rcvd_amt[oid],
                                rcvd_cur=rcvd_cur[oid],
                                sent_amt=sent_amt[oid],
                                sent_cur=sent_cur[oid],
                                fees_amt=fees_amt[oid],
                                fees_cur=fees_cur[oid])
                
                desc = f'{tripod.tx_class()} ({label[oid]}): tx id {oid}'
                links = set()

                postings = []
                if tripod.is_transfer():
                    local_acct = account.join(self.account_root, tripod.xfer_cur())
                    remote_acct = Config.network.route(
                        tripod.is_send(), local_acct, tripod.xfer_cur())
                    xfer_amt = amount.Amount(tripod.xfer_amt(), tripod.xfer_cur())
                    xfer_amt_neg = amount.Amount(-tripod.xfer_amt(), tripod.xfer_cur())
                    xfer_cost = common.usd_cost_spec(tripod.xfer_cur())

                    # Attach cost basis to the neg outgoing leg.
                    if tripod.is_receive():
                        postings.append(
                            Posting(local_acct, xfer_amt, None, None, None, None))
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
                                ComputeRcvdCost(rcvd_cur[oid], rcvd_amt[oid],
                                            sent_cur[oid], sent_amt[oid]),
                                None, None, None))
                    postings.append(
                        Posting(debit_acct,
                                amount.Amount(-tripod.sent_amt, tripod.sent_cur),
                                Cost(None, None, None, None),
                                ComputeSentPrice(rcvd_cur[oid], rcvd_amt[oid],
                                             sent_cur[oid], sent_amt[oid]),
                                None, None))

                else:
                    assert False, "Unexpected tripod type"

                # Gate.io charges fees in crypto.  So what we need to do is take
                # the crypto fee amount, book it as a "sale" at current FMV, and
                # the book a fee expense for that amount of USD.
                if tripod.fees_amt:
                    if tripod.fees_cur == "USD":
                        raise Exception("not expecting USD feeds in GateIO")

                    # Price to use for the virtual exchange.  TODO: get real prices.
                    asset_price_in_usd = Decimal('1.0')
                    fees_in_usd = tripod.fees_amt * asset_price_in_usd

                    # Book the sale
                    postings.append(
                        Posting(account.join(self.account_root, tripod.fees_cur),
                                amount.Amount(-fees_amt[oid], tripod.fees_cur),
                                Cost(None, None, None, None),
                                amount.Amount(asset_price_in_usd, "USD"),
                                None, None))

                    # Book the fee
                    postings.append(
                        Posting(account.join(self.account_fees, "USD"),
                                amount.Amount(fees_in_usd, "USD"),
                                None,
                                None,
                                None, None))

                # PnL
                if tripod.sent:
                    if tripod.sent_cur == "USD":
                        raise Exception("not expecting USD disposals in GateIO")
                    postings.append(
                        Posting(self.account_pnl, None, None, None, None, None))

                txn = data.Transaction(meta, date, flags.FLAG_OKAY,
                                       None, desc, data.EMPTY_SET, links,
                                       postings)
                common.attach_timestamp(txn, timestamp)

                entries.append(txn)

        return entries

if __name__ == "__main__":
    importer = GateIOImporter(
        account_root="Assets:GateIO",
        account_external_root="Assets:ALLEXTERNAL",
        account_pnl="Income:PnL",
        account_fees="Expenses:Financial:Fees",
    )
    main(importer)
