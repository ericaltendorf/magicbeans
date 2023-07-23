"""Run importers and reconcile data, using the beancount-import framework
   (https://github.com/jbms/beancount-import)."""

import glob
import os
import json
import sys
from typing import List
from bean_crypto_import.importers.chiawallet import ChiaWalletImporter
from bean_crypto_import.importers.coinbase import CoinbaseImporter
from bean_crypto_import.importers.coinbasepro import CoinbaseProImporter
from bean_crypto_import.importers.gateio import GateIOImporter
import beangulp
from beangulp.importer import Importer

def get_importers() -> List[Importer]:
   importers = []

   # TODO: move these arguments to a config file
   importers.append(CoinbaseImporter(
      account_root="Assets:Coinbase",
      account_external_root="Assets:ALLEXTERNAL",
      account_gains="Income:PnL",
      account_fees="Expenses:Financial:Fees",))

   importers.append(ChiaWalletImporter(
      account_root="Assets:ChiaWallet",
      account_external_root="Assets:ALLEXTERNAL",
      account_mining_income="Income:Mining",
      account_gains="Income:PnL",
      account_fees="Expenses:Financial:Fees",))

   importers.append(GateIOImporter(
      account_root="Assets:GateIO",
      account_external_root="Assets:ALLEXTERNAL",
      account_gains="Income:PnL",
      account_fees="Expenses:Financial:Fees",))

   importers.append(CoinbaseProImporter(
      account_root="Assets:Coinbase",
      account_external_root="Assets:ALLEXTERNAL",
      account_gains="Income:PnL",
      account_fees="Expenses:Financial:Fees",))

   return importers

# def extract():
# def _extract(ctx, src, output, existing, reverse, failfast, quiet):
#     """Extract transactions from documents.

#     Similar to beagulp._extract() but designed to be driven
#     programmatically, returning the list of entries for further
#     processing.
#     """
#     verbosity = -quiet
#     log = utils.logger(verbosity, err=True)
#     errors = exceptions.ExceptionsTrap(log)

#     # Load the ledger, if one is specified.
#     existing_entries = loader.load_file(existing)[0] if existing else []

#     extracted = []
#     for filename in _walk(src, log):
#         with errors:
#             importer = identify.identify(ctx.importers, filename)
#             if not importer:
#                 log('') # Newline.
#                 continue

#             # Signal processing of this document.
#             log(' ...', nl=False)

#             # Extract entries.
#             entries = extract.extract_from_file(importer, filename, existing_entries)
#             extracted.append((filename, entries))
#             log(' OK', fg='green')

#         if failfast and errors:
#             break

#     for func in ctx.hooks:
#         extracted = func(extracted, existing_entries)

#     # Reverse sort order, if requested.
#     if reverse:
#         for filename, entries in extracted:
#             entries.reverse()

#     # Serialize entries.
#     extract.print_extracted_entries(extracted, output)

#     if errors:
#         sys.exit(1)

# def add_preamble(extracted, existing):
   # result = []
   # entry = #Transaction()
   # for filepath, entries, account, importer in extracted:
      # for entry in entries:
         # None
# 
   # return result
   #  

if __name__ == '__main__':
    importers = get_importers()
    hooks = []
    cli = beangulp.Ingest(importers, hooks).cli
    cli()