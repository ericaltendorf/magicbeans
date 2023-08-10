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

import dateutil.parser

import beangulp
from beancount.core import account, flags
from beancount.core.amount import Amount
from beancount.core.data import (EMPTY_SET, Cost, Posting, Price, Transaction,
                                 new_metadata)
from beancount.core.number import D, round_to
from beangulp.testing import main
from magicbeans import common
from magicbeans.common import usd_cost_spec
from magicbeans.config import Config
from magicbeans.transfers import Link, Network
import pytz


class CoinbaseProImporter(beangulp.Importer):

    # TODO: Migrate from passing in network to passing in config
    def __init__(self, account_root, account_pnl, account_fees, network: Network, config: Config = None):
        self.account_root = account_root
        self.account_pnl = account_pnl
        self.account_fees = account_fees
        self.network = network
        self.config = config

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

    # TODO: we could probably clean a lot of this up by using Tripod.
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
                    tx_ts = dateutil.parser.parse(transfer["time"]).astimezone(pytz.utc)
                    

                    value = D(transfer['amount'])
                    currency = transfer['amount/balance unit']
                    local_account = account.join(self.account_root, currency)

                    title = ""
                    remote_account = "UNDETERMINED"
                    if transfer['type'] == 'deposit':
                        title = f"CBP: Deposit {currency}"
                        remote_account = self.network.source(local_account, currency)
                    if transfer['type'] == 'withdrawal':
                        title = f"CBP: Withdraw {currency}"
                        remote_account = self.network.target(local_account, currency)

                    # value appears to be negated for withdrawals already
                    posting1 = Posting(local_account,
                                       common.rounded_amt(value, currency),
                                       usd_cost_spec(currency), None, None, None)
                    posting2 = Posting(remote_account,
                                       common.rounded_amt(-value, currency),
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
                        tx_ts = dateutil.parser.parse(transfer["time"]).astimezone(pytz.utc)
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
                    title = f' {increase_amount} {increase_currency} with {reduce_amount} {reduce_currency}'
                    postings.append(
                        Posting(f'{self.account_root}:{increase_currency}',
                                common.rounded_amt(increase_amount, increase_currency),
                                cost_amount, None, None, None),
                    )
                    postings.append(
                        Posting(f'{self.account_root}:{reduce_currency}',
                                common.rounded_amt(-reduce_amount + fee_amount, reduce_currency),
                                None, None, None, None)
                    )
                    if fee_currency:
                        if fee_currency != "USD":
                            raise Exception("Haven't implemented non-USD fee disposal here yet")
                        postings.append(
                            Posting(self.account_fees,
                                    common.rounded_amt(-fee_amount, fee_currency),
                                    None, None, None, None)
                        )

                else: # Sell or Swap
                    if trade_type == 'Sell':
                        price = common.rounded_amt(increase_amount/reduce_amount, 'USD')
                        title = f' {reduce_amount} {reduce_currency} for {increase_amount} {increase_currency}'
                    else:
                        price = None
                        title = f' {reduce_amount} {reduce_currency} ' \
                                f'for {increase_amount} {increase_currency}'
                    postings.append(
                        Posting(f'{self.account_root}:{reduce_currency}',
                                common.rounded_amt(-reduce_amount, reduce_currency),
                                Cost(None, None, None, None),
                                price, None, None),
                    )

                    increase_currency_cost_entry = None
                    if increase_currency != "USD":
                        currency_price = (self.config.get_price_fetcher()
                                          .get_price(increase_currency, tx_ts))
                        increase_currency_cost_entry = Cost(currency_price, "USD", None, None)

                    postings.append(
                        Posting(f'{self.account_root}:{increase_currency}',
                                common.rounded_amt(increase_amount, increase_currency),
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
                                    common.rounded_amt(fee_amount, fee_currency),
                                    None if fee_currency == "USD" else Cost(None, None, None, None),
                                    None, None, fee_metadata)
                        )
                        
                        assert fee_currency in ["USD", "USDT"]
                        fee_currency_price_in_usd = D('1.0')
                        if fee_currency == "USDT":
                            fee_currency_price_in_usd = (self.config.get_price_fetcher()
                                                         .get_price(fee_currency, tx_ts))

                        usd_fee_amount = fee_amount * fee_currency_price_in_usd

                        # This is the increase in the account that accumulates all fees,
                        # and must be recorded in USD.
                        postings.append(
                            Posting(self.account_fees,
                                    common.rounded_amt(-usd_fee_amount, "USD"),
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
    
    @staticmethod
    def test_instance():
        return CoinbaseProImporter(
            account_root="Assets:Coinbase",
            account_pnl="Income:PnL",
            account_fees="Expenses:Fees",
            network=Network([Link("Coinbase", "Bank", "USD"),
                             Link("Coinbase", "Ledger", "BTC")],
                            untracked_institutions=["Bank", "Ledger"])
        )

if __name__ == "__main__":
    main(CoinbaseProImporter.test_instance())
