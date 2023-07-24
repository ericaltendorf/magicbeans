"""Read a beancount file and sort by timestamp"""

import sys
from typing import List
from beancount.parser import parser
from beancount.parser import printer
import dateutil.parser

def key(entry):
     return (entry.date, dateutil.parser.parse(entry.meta['timestamp']))

if __name__ == '__main__':
   entries, errors, options = parser.parse_file(sys.argv[1])
   entries.sort(key=key)
   printer.print_entries(entries)