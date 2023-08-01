"""Importer for CoinbasePro "account.csv" csv's.  Derived from
   https://github.com/reedlaw/beancount_coinbase_pro/blob/main/importer.py ,
   updating to the new Beangulp API, cleaning up, and fixing a few bugs.
"""

# TODOs:
# - use "balance" values from the account.csv
# - crypto withdrawals just include the network fee as part of the
#   withdrawal without calling it out separately.  This will cause
#   "lost" value.

__copyright__ = "Copyright (C) 2023  Eric Altendorf"
__license__ = "GNU GPLv2"

import csv
import datetime
import json
import os
import re
from itertools import groupby
from os import path
from magicbeans import common
import dateutil.parser

from beancount.core import account
from beancount.core.amount import Amount
from beancount.core.data import EMPTY_SET, new_metadata, Cost, Posting, Price, Transaction
from beancount.core import flags
from beancount.core.number import D, round_to

import beangulp
from beangulp.testing import main

from magicbeans.common import usd_cost_spec

# TODO: create a better way of encapsulating personal logic
from magicbeans.config import Config

class CoinbaseProImporter(beangulp.Importer):

    def __init__(self, account_root, account_pnl, account_fees):
        self.account_root = account_root
        self.account_pnl = account_pnl
        self.account_fees = account_fees

    def name(self) -> str:
        return 'Coinbase Pro'

    def identify(self, filepath) -> bool:
        if not re.match("^account.csv$", path.basename(filepath)):
            return False

        expected_header = "portfolio,type,time,amount,balance,amount/balance " \
                          "unit,transfer id,trade id,order id"
        if not common.file_begins_with(filepath, expected_header):
            return False 
            
        return True

    def account(self, filepath):
        return self.account_root

    def extract(self, file, existing_entries=None) -> list:
        with open(file, 'r') as _file:
            transactions = list(csv.DictReader(_file))
        entries = []
        sorted_transactions = sorted(
            transactions,
            key=lambda tx: (tx['time'], tx['type']),
        )
        transactions_by_order = groupby(
            transactions,
            lambda tx: tx['order id'],
        )
        for order_id, transfers in transactions_by_order:
            if order_id == '':
                for transfer in transfers:
                    tx_ts = dateutil.parser.parse(transfer["time"])
                    value = D(transfer['amount'])
                    currency = transfer['amount/balance unit']
                    local_account = account.join(self.account_root, currency)

                    title = ""
                    remote_account = "UNDETERMINED"
                    if transfer['type'] == 'deposit':
                        title = f"CBP: Deposit {currency}"
                        remote_account = Config.network.source(local_account, currency)
                    if transfer['type'] == 'withdrawal':
                        title = f"CBP: Withdraw {currency}"
                        remote_account = Config.network.target(local_account, currency)

                    # value appears to be negated for withdrawals already
                    posting1 = Posting(local_account, Amount(value, currency),
                                       usd_cost_spec(currency), None, None, None)
                    posting2 = Posting(remote_account, Amount(-value, currency),
                                       usd_cost_spec(currency), None, None, None)

                    metadata = {'transferid': transfer['transfer id']}
                    tx = Transaction(
                        new_metadata(file, 0, metadata), tx_ts.date(),
                        flags.FLAG_OKAY, None, title,
                        EMPTY_SET, EMPTY_SET,
                        [posting1, posting2]
                        # [withdrawal, deposit],
                    )
                    common.attach_timestamp(tx, tx_ts)

                    # If transfers have fees, then here we should use
                    # split_out_marked_fees(), but apparently coinbase pro
                    # transfers don't have fees?  TODO: check.

                    entries.append(tx)

            else:
                fee_amount = D("0")
                fee_currency = None
                increase_amount = D("0")
                increase_currency = None
                reduce_amount = D("0")
                reduce_currency = None
                postings = []
                title = ' '
                trade_type = None
                tx_ts = None

                for transfer in transfers:
                    if tx_ts is None:
                        tx_ts = dateutil.parser.parse(transfer["time"])
                    metadata = {'orderid': transfer['order id']}
                    currency = transfer['amount/balance unit']
                    value = D(transfer['amount'])
                    local_account = f'{self.account_root}:{currency}'

                    if transfer['type'] == 'match':
                        if value < 0:
                            reduce_amount -= value
                            if reduce_currency is None:
                                reduce_currency = currency
                            if reduce_currency == 'USD':
                                trade_type = 'Buy'
                            if trade_type is None:
                                trade_type = 'Swap'
                        else:
                            increase_amount += value
                            if increase_currency is None:
                                increase_currency = currency
                            if increase_currency == 'USD':
                                trade_type = 'Sell'
                            if trade_type is None:
                                trade_type = 'Swap'

                    if transfer['type'] == 'fee':
                        fee_amount += value
                        if fee_currency is None:
                            fee_currency = currency


                if trade_type == 'Buy':
                    cost_amount = Cost(reduce_amount/increase_amount, 'USD', None, None)
                    title = f' {increase_amount} {increase_currency}'
                    postings.append(
                        Posting(f'{self.account_root}:{increase_currency}',
                                Amount(increase_amount, increase_currency),
                                cost_amount, None, None, None),
                    )
                    postings.append(
                        Posting(f'{self.account_root}:{reduce_currency}',
                                Amount(-reduce_amount + fee_amount, reduce_currency),
                                None, None, None, None)
                    )
                    if fee_currency:
                        if fee_currency != "USD":
                            raise Exception("Haven't implemented non-USD fee disposal here yet")
                        postings.append(
                            Posting(self.account_fees,
                                    Amount(-fee_amount, fee_currency),
                                    None, None, None, None)
                        )

                else: # Sell or Swap
                    if trade_type == 'Sell':
                        price = Amount(increase_amount/reduce_amount, 'USD')
                        title = f' {reduce_amount} {reduce_currency}'
                    else:
                        price = None
                        title = f' {reduce_amount} {reduce_currency} ' \
                                f'for {increase_amount} {increase_currency}'
                    postings.append(
                        Posting(f'{self.account_root}:{reduce_currency}',
                                Amount(-reduce_amount, reduce_currency),
                                Cost(None, None, None, None),
                                price, None, None),
                    )

                    increase_currency_cost_entry = None
                    if increase_currency != "USD":
                        # TODO: get real price of currency
                        increase_currency_cost_entry = Cost(D('1.0'), "USD", None, None)

                    postings.append(
                        Posting(f'{self.account_root}:{increase_currency}',
                                Amount(increase_amount, increase_currency),
                                increase_currency_cost_entry, None, None, None),
                    )
                    if fee_currency:
                        # TODO: clarify this comment:
                        # Fees don't show up in the reduce amount for some reason,
                        # so we add an extra posting to cover the debiting of fees.

                        fee_metadata = None if fee_currency == "USD" else {'is_fee': True}
                        
                        # This is the decrease in the account which paid the fee.  If not
                        # in USD, we must supply a cost.
                        postings.append(
                            Posting(account.join(self.account_root, fee_currency),
                                    Amount(fee_amount, fee_currency),
                                    None if fee_currency == "USD" else Cost(None, None, None, None),
                                    None, None, fee_metadata)
                        )
                        
                        # TODO: generalize and use real prices
                        assert fee_currency in ["USD", "USDT"]
                        fee_currency_price_in_usd = D('1.0')

                        usd_fee_amount = fee_amount * fee_currency_price_in_usd

                        # This is the increase in the account that accumulates all fees,
                        # and must be recorded in USD.
                        postings.append(
                            Posting(self.account_fees,
                                    Amount(-usd_fee_amount, "USD"),
                                    None, None, None, fee_metadata)
                        )
                        if fee_metadata:
                            postings.append(
                                Posting(self.account_pnl, None, None, None, None, fee_metadata)
                            )
                        
                    postings.append(
                        Posting(self.account_pnl, None, None, None, None, None)
                    )

                tx = Transaction(
                    new_metadata(file, 0, metadata),
                    tx_ts.date(),
                    flags.FLAG_OKAY,
                    None,
                    f'CBP: {trade_type}{title}',
                    EMPTY_SET,
                    EMPTY_SET,
                    postings,
                )
                common.attach_timestamp(tx, tx_ts)

                (reg_tx, fee_tx) = common.split_out_marked_fees(tx, self.account_pnl)
                if reg_tx and fee_tx:
                    entries.append(reg_tx)
                    entries.append(fee_tx)
                else:
                    entries.append(tx)

        return entries
    

if __name__ == "__main__":
    importer = CoinbaseProImporter(
        account_root="Assets:Coinbase",
        account_pnl="Income:PnL",
        account_fees="Expenses:Financial:Fees",
    )
    main(importer)
