"""Importer for Coinbase "TransactionHistoryReport" csv's.  Derived from
   UTrade example by Martin Blais.
"""
__copyright__ = "Copyright (C) 2023  Eric Altendorf"
__license__ = "GNU GPLv2"

import csv
import datetime
import logging
import re
from decimal import Decimal
from os import path
from typing import NamedTuple

import dateutil.parser

import beangulp
from beancount.core import account, amount, data, flags, position
from beancount.core.position import Cost
from beancount.core.amount import Amount
from beancount.core.number import ZERO, D
from beangulp.testing import main
from magicbeans import common
from magicbeans.transfers import Link, Network


def coinbase_data_reader(reader):
    """A wrapper for a FileReader which will skip Coinbase CSV header cruft"""
    found_content = False
    for line in reader:
        if line.startswith("Timestamp,Transaction Type,Asset,Quantity Transacted,"):
            found_content = True
        if found_content:
            yield line

class CoinbaseImporter(beangulp.Importer):
    """An importer for Coinbase CSV files."""

    def __init__(self, account_root, account_gains, account_fees, network: Network):
        self.account_root = account_root
        self.account_gains = account_gains
        self.account_fees = account_fees
        self.network = network

    def name(self) -> str:
        return 'Coinbase'

    def identify(self, filepath):
        filename_re = r"^Coinbase-.*TransactionsHistoryReport-" \
                      r"\d\d\d\d-\d\d-\d\d-\d\d-\d\d-\d\d.csv$"
        if not re.match(filename_re, path.basename(filepath)):
            return False
        
        expected_header = '"You can use this transaction report to inform ' \
                          'your likely tax obligations.'
        if not common.file_begins_with(filepath, expected_header):
            return False
            
        return True

    def filename(self, filepath):
        return "coinbase.{}".format(path.basename(filepath))

    def account(self, filepath):
        return self.account_root

    def date(self, filepath):
        # Extract the statement date from the filename.
        date_re = r"Coinbase-.*TransactionsHistoryReport-" \
                  r"(\d\d\d\d-\d\d-\d\d)-\d\d-\d\d-\d\d.csv"
        m = re.match(date_re, path.basename(filepath))
        return datetime.datetime.strptime(m.group(1), "%Y-%m-%d").date()

    def extract(self, filepath, existing):
        # Open the CSV file and create directives.
        entries = []
        index = 0
        with open(filepath) as infile:
            # TODO: this reader wrapper breaks the line numbers
            reader = coinbase_data_reader(infile)
            for index, row in enumerate(csv.DictReader(reader)):
                meta = data.new_metadata(filepath, index)

                timestamp = dateutil.parser.parse(row["Timestamp"])
                date = timestamp.date()
                rtype = row["Transaction Type"].lstrip("Advanced Trade ")
                instrument = row["Asset"]
                quantity = D(row["Quantity Transacted"])
                fees = row["Fees and/or Spread"]
                asset_price_currency = row["Spot Price Currency"]
                reported_asset_price = D(row["Spot Price at Transaction"])
                subtotal = D(row['Subtotal'])
                total = D(row["Total (inclusive of fees and/or spread)"])

                total_amount = common.rounded_amt(total, asset_price_currency)
                units = common.rounded_amt(quantity, instrument)
                fees = common.rounded_amt(D(fees), asset_price_currency)
                account_cash = account.join(self.account_root, asset_price_currency)
                account_inst = account.join(self.account_root, instrument)

                desc = "CB: " + row["Notes"].replace("Bought", "Buy").replace("Sold", "Sell")
                links = set()  # { "ut{0[REF #]}".format(row) }

                if rtype in ("Send", "Receive"):
                    assert fees.number == ZERO

                    account_external = "UNDETERMINED"
                    if rtype == "Send":
                        account_external = self.network.target(account_inst, instrument)
                    else:
                        account_external = self.network.source(account_inst, instrument)

                    sign = Decimal(1 if (rtype == "Receive") else -1)
                    txn = data.Transaction(meta, date, flags.FLAG_OKAY,
                                           None, desc, data.EMPTY_SET, links,
                        [
                            data.Posting(account_inst, amount.mul(units, sign),
                                         common.usd_cost_spec(instrument), None, None, None),
                            data.Posting(account_external, amount.mul(units, -sign),
                                         common.usd_cost_spec(instrument), None, None, None),
                        ],
                    )

                elif rtype in ("Buy", "Sell"):
                    # Used as cost for buys, proceeds for sells.
                    fee_adjusted_value = total / quantity
                    desc += f' (@{reported_asset_price}, ' \
                            f"w fees ~{fee_adjusted_value:.4f})"
                            
                    meta['fee-info'] = f"(fees={fees}, total={total}, subtotal={subtotal}); "\
                        f"fee-adjusted per-unit value: {fee_adjusted_value} {asset_price_currency}"

                    if rtype == "Buy":
                        postings = [
                            data.Posting(account_inst, units,
                                        Cost(fee_adjusted_value, asset_price_currency, None, None),
                                        None, None, None),
                            data.Posting(account_cash, -total_amount,
                                         None, None, None, None),
                        ]
                    else:
                        postings = [
                            data.Posting(account_inst, -units,
                                        Cost(None, None, None, None),
                                        Amount(fee_adjusted_value, asset_price_currency),
                                        None, None),
                            data.Posting(account_cash, total_amount,
                                        None, None, None, None),
                            data.Posting(self.account_gains,
                                         None, None, None, None, None),
                        ]

                    txn = data.Transaction(meta, date, flags.FLAG_OKAY, None,
                                           desc, data.EMPTY_SET, links, postings)

                else:
                    logging.error("Unknown row type: %s; skipping", rtype)
                    continue
                common.attach_timestamp(txn, timestamp)
                entries.append(txn)

        return entries

    # Example usage; also enables running integration tests
    @staticmethod
    def test_instance():
        return CoinbaseImporter(
            account_root="Assets:Coinbase",
            account_gains="Income:PnL",
            account_fees="Expenses:Financial:Fees",
            network=Network([Link("Coinbase", "Bank", "USD"),
                            Link("Coinbase", "Ledger", "BTC")],
                            untracked_institutions=["Bank", "Ledger"])
        )

if __name__ == "__main__":
    main(CoinbaseImporter.test_instance())
