##############################################################################
#
# This is an example local config for Magicbeans.  You will want to modify this
# for your own setup.  You probably want to copy it into a private repo so
# that you can track changes and keep account info private.
#
##############################################################################

import datetime
import dateutil
from decimal import Decimal
from typing import Callable, List
from beancount.core.amount import Amount

import magicbeans
from beancount.core.data import Transaction, create_simple_posting
from beangulp.importer import Importer
from magicbeans import common, transfers
from magicbeans.common import ExtractionRecord
from magicbeans.importers.chiawallet import ChiaWalletImporter
from magicbeans.importers.coinbase import CoinbaseImporter
from magicbeans.importers.coinbasepro import CoinbaseProImporter
from magicbeans.importers.gateio import GateIOImporter

#
# Set up your Beancount initializations and settings here.
#

preamble = """
;; -*- mode: beancount; coding: utf-8; fill-column: 400; -*-

option "title" "Crypto Trading"
option "operating_currency" "USD"
option "booking_method" "HIFO"
option "inferred_tolerance_default" "USD:0.01"

;; Use the cap gains plugin.

plugin "beancount_reds_plugins.capital_gains_classifier.long_short" "{
  'Income.*:CapGains': [':CapGains', ':CapGains:Short', ':CapGains:Long']
  }"

;; Virtual accounts for tracking and padding.

2000-01-01 open Equity:Opening-Balances
2000-01-01 open Equity:Unexplained
2000-01-01 open Expenses:Fees
2000-01-01 open Income:CapGains
2000-01-01 open Income:CapGains:Short
2000-01-01 open Income:CapGains:Long
2000-01-01 open Income:Mining:USD

;; Set up USD accounts.  You can set balances to real values if
;; you like, but if you're only calculating cap gains it doesn't
;; matter what your USD account starting balance is.

2010-01-01 pad Assets:Coinbase:USD Equity:Opening-Balances
2010-01-01 pad Assets:Bank:USD Equity:Opening-Balances
2010-01-02 balance Assets:Coinbase:USD 10000000.00 USD
2010-01-02 balance Assets:Bank:USD 10000000.00 USD

;; Optional: balance assertions at particular dates
;; to increase confidence.  E.g.:
;;
;;      2020-01-01 balance Assets:Coinbase:BTC 1.0000000000000000 BTC

;; Optional: manual padding for discrepencies.
;;
;;      2021-01-01 * "Manual padding to account for some unexplained lost funds (unaccounted fees?)"
;;        Equity:Unexplained 0.00003708 BTC
;;        Assets:Wallet:BTC -0.00003708 BTC
"""

#
# The basic configuration for Magicbeans
#

class LocalConfig(magicbeans.config.Config):

    def __init__(self):
        super().__init__()

    # Set up the network defining how transfers happen for you.  See the
    # transfers.Network class for more details.
    def get_network(self):
        network = transfers.Network([
            transfers.Link("Coinbase", "Bank", "USD"),
            transfers.Link("Coinbase", "GateIO", "USDT"),
            transfers.Link("Coinbase", "Wallet", "BTC"),
            transfers.Link("Coinbase", "Wallet", "ETH"),
            transfers.Link("Coinbase", "Wallet", "LTC"),
            transfers.Link("GateIO", "ChiaWallet", "XCH"),
        ], ["Bank", "Wallet"])
        return network

    # Set up the importers you want to use, attaching them to the appropriate
    # accounts.  TODO: move these arguments to a config file
    def get_importers(self) -> List[Importer]:
        network = self.get_network()
        importers = []

        importers.append(CoinbaseImporter(
            account_root="Assets:Coinbase",
            account_gains="Income:CapGains",
            account_fees="Expenses:Fees",
            network=network))

        importers.append(CoinbaseProImporter(
            account_root="Assets:Coinbase",
            account_pnl="Income:CapGains",
            account_fees="Expenses:Fees",
            network=network,
            config=self))

        # Less popular examples:

        # importers.append(ChiaWalletImporter(
            # account_root="Assets:ChiaWallet",
            # account_mining_income="Income:Mining",
            # account_gains="Income:CapGains",
            # account_fees="Expenses:Fees",
            # network=network,
            # config=self,
            # chiawallet_config_path="path-to/chiawallet_config.yaml"))

        # importers.append(GateIOImporter(
            # account_root="Assets:GateIO",
            # account_pnl="Income:CapGains",
            # account_fees="Expenses:Fees",
            # config=self))

        return importers

    # Define the hooks that should be run on the transactions.
    def get_hooks(self) -> List[Callable[
            [List[ExtractionRecord], List[Transaction]],
            List[ExtractionRecord]]]:
        return [chiawallet_filter_change_coins_hook,
                cbp_tweak_xfer_timestamp_hook,
                chiawallet_recharacterize_sale_hook,
                ]

    def get_price_fetcher(self):
        return self.price_fetcher

    # This is a little weird; the price fetcher is now created and set by the
    # framework main run routine, but still accessed via the local Config.
    def set_price_fetcher(self, price_fetcher):
        self.price_fetcher = price_fetcher

    def get_preamble(self):
        return preamble

#
# Example hooks (ie Beangulp hooks).  These are for illustration purposes; you
# should write your own to tweak your data as needed.
#
# Hooks should take arguments:
#   extracted: List[common.ExtractionRecord]
#   existing_entries: List[Transaction]
# and return a new
#   List[common.ExtractionRecord]
#
# Unfortunately these types are not really defined or documented; please refer
# to the Beangulp source code for more information.
#

def chiawallet_filter_change_coins_hook(extracted: List[ExtractionRecord], _existing_entries: List[Transaction]) -> List[ExtractionRecord]:
    return common.filter_extractions(extracted, chiawallet_filter_change_coins)

def chiawallet_filter_change_coins(entry: Transaction):
    """The chia wallet sometimes has trouble accurately reporting change from
    a UTXO spend.  These are change coins that show up as solo receives instead
    of netting out against the spend.  Filter them."""
    to_filter = [
        ('2022-01-02T18:20:55Z', Decimal("1.74999999")),
        ('2022-02-08T08:45:10Z', Decimal("1.749999")),
    ]   
    return (isinstance(entry, Transaction) and
            (entry.meta['timestamp'], entry.postings[0].units.number) in to_filter)


def cbp_tweak_xfer_timestamp_hook(extracted: List[ExtractionRecord], _existing_entries: List[Transaction]) -> List[ExtractionRecord]:
    return [ExtractionRecord(filename, map(cbp_tweak_xfer_timestamp, entries), account, importer)
            for (filename, entries, account, importer) in extracted]

def cbp_tweak_xfer_timestamp(tx: Transaction) -> Transaction:
    """Adjust timestamps on transactions, which were transfers of USDT from CBP
    to GateIO, but which show up in GateIO some minutes before CBP registers
    it, which throws off all the bookkeeping.  Tweak the timestamp to send
    before it's received."""
    minutes_to_backdate = None
    if ('transferid' in tx.meta):
        if (tx.meta['transferid'] == 'abcd1234-12ab-abcd-1234-09876abcdef0'):
            minutes_to_backdate = 5
    if minutes_to_backdate:
        orig_ts = dateutil.parser.parse(tx.meta['timestamp'])
        new_ts = orig_ts + datetime.timedelta(minutes=-minutes_to_backdate)
        tx.meta['backdated-by'] = f"{minutes_to_backdate} minutes"
        common.attach_timestamp(tx, new_ts)
    return tx   # So can be used in map()


def chiawallet_recharacterize_sale_hook(extracted: List[ExtractionRecord], _existing_entries: List[Transaction]) -> List[ExtractionRecord]:
    return [ExtractionRecord(filename, map(chiawallet_recharacterize_sale_entry, entries), account, importer)
            for (filename, entries, account, importer) in extracted]

def chiawallet_recharacterize_sale_entry(entry: Transaction) -> Transaction:
    """Handle some transactions which appears to simply be a Send transaction,
    but which were actually transfers to a buyer, in exchange for USD.  Namely,
    recharacterize them as a sale instead of a Send."""
    to_recharacterize = [
        ("2022-01-01T09:30:15Z", "Send 1.0000 XCH"),
        ("2022-01-01T09:45:50Z", "Send 2.0000 XCH"),
    ]
    if isinstance(entry, Transaction) and (entry.meta['timestamp'], entry.narration) in to_recharacterize:
        new_narration = entry.narration.replace("Send", "Sell") + " at 100.0 USD/XCH"
        new_entry = entry._replace(narration=new_narration)
        new_entry.meta['original_narration'] = entry.narration

        assert len(new_entry.postings) == 2
        debit_leg = next(filter(lambda p: p.units.number < 0, new_entry.postings))
        credit_leg = next(filter(lambda p: p.units.number > 0, new_entry.postings))
        assert debit_leg
        assert credit_leg
        new_entry.postings.clear()

        price = Decimal("100.0")

        # Construct the debit leg with price and add it
        debit_leg = debit_leg._replace(price = Amount(price, "USD"))
        new_entry.postings.append(debit_leg)

        # Replace the credit leg
        usd_amount = - debit_leg.units.number * price
        create_simple_posting(new_entry, "Assets:Bank:USD", usd_amount, "USD")

        # Add the cap gains leg
        create_simple_posting(new_entry, "Income:CapGains", None, None)

        return new_entry   # So can be used in map()
    else:
        return entry