"""Importer for transactions from a Chia wallet (https://www.chia.net/).
   Actually, this currently imports a highly preprocessed csv that is
   produced by another very Chia-specific script (outside this repo)
   from the raw Chia wallet dump.  In the future we may integrate that
   script.
"""
__copyright__ = "Copyright (C) 2023  Eric Altendorf"
__license__ = "GNU GPLv2"

import csv
import datetime
from decimal import Decimal
from typing import NamedTuple
import re
import logging
from magicbeans.transfers import Link, Network
import pytz

from os import path
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

from magicbeans import common
from magicbeans.tripod import Tripod

# Surprisingly the Chia wallet dumps seem to be in local (PST) time.
# For now, we'll convert to UTC.  TODO: fix the Chia wallet dumper to
# report in UTC?
rendered_tz = 'US/Pacific'

class ChiaWalletImporter(beangulp.Importer):
    """An importer for Coinbase CSV files."""

    def __init__(self, account_root, account_mining_income,
                 account_gains, account_fees, network: Network):
        self.account_root = account_root
        self.account_mining_income = account_mining_income
        self.account_gains = account_gains
        self.account_fees = account_fees
        self.network = network

    def name(self) -> str:
        return 'ChiaWallet'

    def identify(self, filepath):
        filename_re = r"^chiawallet.\d\d\d\d.\d\d.\d\d.csv$"
        if not re.match(filename_re, path.basename(filepath)):
            return False
            
        expected_header = 'Date,Received Quantity,Received Currency,Sent Quantity,' \
                          'Sent Currency,Fee Amount,Fee Currency,Tag'
        if not common.file_begins_with(filepath, expected_header):
            return False

        return True

    def filename(self, filepath):
        return "coinbase.{}".format(path.basename(filepath))

    def account(self, filepath):
        return self.account_root

    def date(self, filepath):
        # Extract the statement date from the filename.
        return datetime.datetime.strptime(path.basename(filepath),
                                          "chiawallet.%Y.%m.%d.csv").date()

    def extract(self, filepath, existing):
        # Open the CSV file and create directives.
        entries = []
        index = 0

        with open(filepath) as infile:
            for index, row in enumerate(csv.DictReader(infile)):
                meta = data.new_metadata(filepath, index)

                # date = parse(row["Date"]).date()
                # Translate timestamps and record timestamp windows
                naive_dt = datetime.datetime.strptime(row['Date'], '%m/%d/%Y %H:%M:%S')
                local_dt = pytz.timezone(rendered_tz).localize(naive_dt)
                utc_dt = local_dt.astimezone(pytz.timezone('UTC'))
 
                tripod = Tripod(row["Received Quantity"],
                                row["Received Currency"],
                                row["Sent Quantity"],
                                row["Sent Currency"],
                                row["Fee Amount"],
                                row["Fee Currency"])

                tag = row["Tag"]
                if tag == "mined":
                    assert tripod.is_transfer()

                desc = ""
                if tag == "mined":
                    desc = f"Mining reward of {tripod.amount()} {tripod.currency()}"
                elif tripod.is_transfer():
                    desc = f"{tripod.tx_class()} {tripod.amount()} {tripod.currency()}"
                else:
                    desc = "Unexpected transaction??"

                links = data.EMPTY_SET

                if tripod.is_transfer():
                    account_int = account.join(self.account_root, tripod.currency())

                    if tag == "mined":
                        account_ext = account.join(self.account_mining_income,
                                                   "USD")  # TODO
                    else:
                        if tripod.rcvd:
                            account_ext = self.network.source(account_int, tripod.currency())
                        else:
                            account_ext = self.network.target(account_int, tripod.currency())

                    units = amount.Amount(tripod.amount(), tripod.currency())
                    sign = Decimal(1 if tripod.rcvd else -1)

                    # Just to get things running, assign all XCH a cost basis of 1 USD
                    # TODO: fix
                    mined_cost_basis = position.Cost(D("1.0"), "USD", None, None)

                    txn = data.Transaction(meta, utc_dt.date(), flags.FLAG_OKAY,
                                           None, desc, data.EMPTY_SET, links,
                        [
                            data.Posting(account_int,
                                         amount.mul(units, sign),
                                         mined_cost_basis if (tag == "mined") else common.usd_cost_spec(tripod.currency()),
                                         None, None, None),
                            data.Posting(account_ext,
                                         None if (tag == "mined") else amount.mul(units, -sign),
                                         None if (tag == "mined") else common.usd_cost_spec(tripod.currency()),
                                         None, None, None),
                        ],
                    )
                    common.attach_timestamp(txn, utc_dt)

                elif tripod.is_transaction():
                    assert False, "Unexpected transaction in wallet (expect transfers only)"

                else:
                    assert False, "not handled yet"

                entries.append(txn)

        return entries


if __name__ == "__main__":
    importer = ChiaWalletImporter(
        account_root="Assets:ChiaWallet",
        account_mining_income="Income:Mining",
        account_gains="Income:PnL",
        account_fees="Expenses:Fees",
        network=Network([Link("ChiaWallet", "GateIO", "XCH")],
                        untracked_institutions=[])  # not particularly relevant
    )
    main(importer)
