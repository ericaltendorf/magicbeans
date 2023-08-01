"""Run importers and reconcile data, using the beancount-import framework
   (https://github.com/jbms/beancount-import)."""

from typing import List
from magicbeans import config
import beangulp

if __name__ == '__main__':
   network = config.get_network()
   importers = config.get_importers(network)
   hooks = config.get_hooks()

   ingest = beangulp.Ingest(importers, hooks)
   ingest()