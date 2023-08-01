"""Run importers and reconcile data, using the beancount-import framework
   (https://github.com/jbms/beancount-import)."""

import glob
import os
import json
import sys
from typing import List
from magicbeans import config, transfers
from magicbeans.importers.chiawallet import ChiaWalletImporter
from magicbeans.importers.coinbase import CoinbaseImporter
from magicbeans.importers.coinbasepro import CoinbaseProImporter
from magicbeans.importers.gateio import GateIOImporter
import beangulp
from beangulp.importer import Importer

if __name__ == '__main__':
    network = config.get_network()
    importers = config.get_importers(network)
    hooks = config.get_hooks()

    cli = beangulp.Ingest(importers, hooks).cli
    cli()