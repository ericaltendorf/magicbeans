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

from common import usd_cost_spec
from tripod import Tripod

class ChiaWalletImporter(beangulp.Importer):
    """An importer for Coinbase CSV files."""

    def __init__(self, account_root, account_external_root,
                 account_mining_income, account_gains, account_fees):
        self.account_root = account_root
        self.account_external_root = account_external_root
        self.account_mining_income = account_mining_income
        self.account_gains = account_gains
        self.account_fees = account_fees

    def name(self) -> str:
        return 'ChiaWallet'

    def identify(self, filepath):
        # TODO: make sure all importers use begin & end regexes
        filename_re = r"chiawallet.\d\d\d\d.\d\d.\d\d.csv$"
        if not re.match(filename_re, path.basename(filepath)):
            return False
        
        # TODO: factor this common header pattern out into commom.py
        with open(filepath, "r") as file:
            expected = 'Date,Received Quantity,Received Currency,Sent Quantity,Sent Currency,Fee Amount,Fee Currency,Tag'
            head = file.read(len(expected))
            if (head != expected):
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

                date = parse(row["Date"]).date()

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
                    desc = f"Transfer of {tripod.amount()} {tripod.currency()}"
                else:
                    desc = "Unexpected transaction??"

                links = data.EMPTY_SET

                if tripod.is_transfer():
                    account_int = account.join(self.account_root, tripod.currency())
                    if tag == "mined":
                        account_ext = account.join(self.account_mining_income,
                                                   tripod.currency())
                    else:
                        account_ext = account.join(self.account_external_root,
                                                   tripod.currency())

                    units = amount.Amount(tripod.amount(), tripod.currency())
                    sign = Decimal(1 if tripod.rcvd else -1)
                    txn = data.Transaction(meta, date, flags.FLAG_OKAY,
                                           None, desc, data.EMPTY_SET, links,
                        [
                            data.Posting(account_int,
                                         amount.mul(units, sign),
                                         usd_cost_spec(), None, None, None),
                            data.Posting(account_ext,
                                         amount.mul(units, -sign),
                                         usd_cost_spec(), None, None, None),
                        ],
                    )

                elif tripod.is_transaction():
                    assert False, "Unexpected transaction in wallet (expect transfers only)"

                else:
                    assert False, "not handled yet"

                entries.append(txn)

        return entries


if __name__ == "__main__":
    importer = ChiaWalletImporter(
        account_root="Assets:Wallet",
        account_external_root="Assets:ALLEXTERNAL",
        account_mining_income="Income:Mining",
        account_gains="Income:PnL",
        account_fees="Expenses:Financial:Fees",
    )
    main(importer)
