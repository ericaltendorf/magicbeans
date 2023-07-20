"""Run importers and reconcile data, using the beancount-import framework
   (https://github.com/jbms/beancount-import)."""

import glob
import os
import json
import sys


def run_reconcile(extra_args):
   # import beancount_import.webserver

   journal_dir = os.path.dirname(__file__)
   data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

   data_sources = [ ]

   # beancount_import.webserver ...
