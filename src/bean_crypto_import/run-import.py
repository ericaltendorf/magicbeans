"""Run importers and reconcile data, using the beancount-import framework
   (https://github.com/jbms/beancount-import)."""

import glob
import os
import json
import sys

from bean_crypto_import.importers.coinbase import CoinbaseImporter

# TODO: factor this out
cb_importer = CoinbaseImporter(
   account_root="Assets:Coinbase",
   account_external_root="Assets:ALLEXTERNAL",
   account_gains="Income:PnL",
   account_fees="Expenses:Financial:Fees",
)

def run_reconcile(extra_args):
   import beancount_import.webserver

   journal_dir = os.path.dirname(__file__)
   data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

   data_sources = [ 
       dict(
         module='beancount_import.source.generic_importer_source',
         importer=cb_importer,
         directory='/home/eric/crypto-taxes/downloads/Coinbase',
       )
   ]

   beancount_import.webserver.main(
      extra_args,
      journal_input=os.path.join(journal_dir, 'journal.beancount'),
      ignored_journal=os.path.join(journal_dir, 'ignored.beancount'),
      default_output=os.path.join(journal_dir, 'transactions.beancount'),
      open_account_output_map=[
         ('.*', os.path.join(journal_dir, 'accounts.beancount')),
      ],
      balance_account_output_map=[
         ('.*', os.path.join(journal_dir, 'accounts.beancount')),
      ],
      price_output=os.path.join(journal_dir, 'prices.beancount'),
      data_sources=data_sources,
   )

if __name__ == '__main__':
    run_reconcile(sys.argv[1:])