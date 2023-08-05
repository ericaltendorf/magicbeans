from collections import namedtuple
import os
from beancount import parser

import beangulp
from beangulp import exceptions, utils
from beangulp import extract
from beangulp import identify
from click import Context
import dateutil


def run(config, input_dir, working_dir):
    """Main entry point.  Runs the whole pipeline.

    Pass in a config with three methods:
    - get_network() -> Network
    - get_importers(network) -> List[Importer]
    - get_hooks() -> List[Hook]
    - get_preamble() -> str

    Example usage is to write a file, e.g. `magicbeans_local.py` which defines
    your own settings and behavior, and then run the pipeline from that file:

        preamble = ('option "title" "Crypto Trading"\n' +
                    'option "operating_currency" "USD\n" + ...)

        class LocalConfig:
            def get_network():
                return transfers.Network(...)
            def get_importers(network):
                return [CoinbaseImporter(...), ... ]
            def get_hooks():
                return [my_hook, ... ]
            def get_preamble():
                return preamble

        def my_hook(extracted, _existing_entries=None):
            return  ....  # this will be simpler after factoring filter/map code out of my own local file

        if __name__ == '__main__':
            config = LocalConfig()
            magicbeans.run.run(config)

    TODO: improve  documentation
    TODO: separate in phases, allow running of subphases
    """

    path_preamble   = os.path.join(working_dir, "00-directives.beancount")
    path_directives = os.path.join(working_dir, "01-directives.beancount")
    path_extracted  = os.path.join(working_dir, "02-extracted.beancount")
    path_sorted     = os.path.join(working_dir, "03-extracted-sorted.beancount")
    path_final      = os.path.join(working_dir, "04-final.beancount")

    network = config.get_network()
    default_date = "2000-01-01"

    # Preamble
    print(f"==== Generating preamble to {path_preamble}...")
    with open(path_preamble, "w") as out:
        out.write(config.get_preamble())

    # Directives
    print(f"==== Generating directives to {path_directives}...")
    with open(path_directives, "w") as out:
        out.write(network.generate_account_directives(default_date))

    # Extract
    print(f"==== Extracting data to {path_extracted}...")
    with open(path_extracted, "w") as out:
        importers = config.get_importers(network)
        hooks = config.get_hooks()
        extract_all(utils.walk([input_dir]), out, importers, hooks)

    # Sort
    print(f"==== Sorting extracted data to {path_sorted}...")
    def ts_key(entry):
        return (entry.date, dateutil.parser.parse(entry.meta['timestamp']))
    with open(path_sorted, "w") as out:
        entries, errors, options = parser.parser.parse_file(path_extracted)
        entries.sort(key=ts_key)
        parser.printer.print_entries(entries, file=out)

    # Join files
    print(f"==== Joining directives and sorted data to {path_final}...")
    with open(path_final, "w") as out:
        for path in [path_preamble, path_directives, path_sorted]:
            with open(path) as infile:
                out.write(infile.read())

    print(f"==== Done!  Final file is {path_final}.")


# Beangulp extract is designed to be called directly from the command
# and has no exposed API.  It's hard to call through all the Click abstractions
# and magic, so instead we just reimplement a very stripped down importer here.
def extract_all(input_filenames, out, importers, hooks):
    existing_entries = []  # Start from scratch each run
    extracted = []
    for filename in input_filenames:
        importer = identify.identify(importers, filename)
        if importer:
            print(f'  {importer.name()} importer processing {filename}')
            entries = extract.extract_from_file(importer, filename, [])
            account = importer.account(filename)
            extracted.append((filename, entries, account, importer))

    # Sort and dedup.
    extract.sort_extracted_entries(extracted)
    for filename, entries, account, importer in extracted:
        importer.deduplicate(entries, existing_entries)
        existing_entries.extend(entries)

    # Invoke hooks.
    for func in hooks:
        extracted = func(extracted, [])

    # Serialize entries.
    extract.print_extracted_entries(extracted, out)


if __name__ == '__main__':
    config = None  # TODO: create some workable default config 
    run(config, "sourcefiles", "workingdir")