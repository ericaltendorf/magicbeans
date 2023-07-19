"""Importer for csv's of processed data from GateIO.
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
from beancount.core.data import Posting
from dateutil.parser import parse

from beancount.core import account
from beancount.core import amount
from beancount.core import data
from beancount.core import flags
from beancount.core import position
from beancount.core.number import D
from beancount.core.number import ZERO

import beangulp
from beangulp.testing import main
import pytz

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

class GateIOImporter(beangulp.Importer):
    """An importer for GateIO csv files."""

    def __init__(self, account_root, account_external_root,
                 account_gains, account_fees):
        self.account_root = account_root
        self.account_external_root = account_external_root
        self.account_gains = account_gains
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

                # TODO: GateIO charges fees in crypto units.  We may want to
                # implicitly convert those to 
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
                    sent_amt[oid] = ch_amt
                    sent_cur[oid] = currency
                    ext_amt[oid] = -ch_amt
                    ext_cur[oid] = currency
                    label[oid] = "Withdraw"

                else:
                    assert False, f"Unknown action {action}"

            for oid in sorted(order_ids, key=tx_ts_min.get):
                date = tx_ts_min[oid].date() #strftime('%m/%d/%Y %H:%M:%S').date()
                
                # TODO
                desc = f"{label[oid]} (tx id {oid})"
                links = set()

                postings = []
                if rcvd_amt[oid] or rcvd_cur[oid]:
                    postings.append(
                        Posting(account.join(self.account_root, rcvd_cur[oid]),
                                amount.Amount(rcvd_amt[oid], rcvd_cur[oid]),
                                None, # cost???
                                None, # price?
                                None, None))

                if sent_amt[oid] or sent_cur[oid]:
                    postings.append(
                        Posting(account.join(self.account_root, sent_cur[oid]),
                                amount.Amount(-sent_amt[oid], sent_cur[oid]),
                                None, # cost???
                                None, # price?
                                None, None))

                if ext_amt[oid] or ext_cur[oid]:
                    postings.append(
                        Posting(account.join(self.account_external_root, ext_cur[oid]),
                                amount.Amount(ext_amt[oid], ext_cur[oid]),
                                None, # cost???
                                None, # price?
                                None, None))
                    
                if fees_amt[oid] or fees_cur[oid]:
                    postings.append(
                        Posting(account.join(self.account_fees, fees_cur[oid]),
                                amount.Amount(fees_amt[oid], fees_cur[oid]),
                                None, # cost???
                                None, # price?
                                None, None))

                txn = data.Transaction(meta, date, flags.FLAG_OKAY,
                                       None, desc, data.EMPTY_SET, links,
                                       postings)

                entries.append(txn)

        return entries



if __name__ == "__main__":
    importer = GateIOImporter(
        account_root="Assets:GateIO",
        account_external_root="Assets:ALLEXTERNAL",
        account_gains="Income:PnL",
        account_fees="Expenses:Financial:Fees",
    )
    main(importer)
