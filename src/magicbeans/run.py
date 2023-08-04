import os
from beancount import parser

import beangulp
import dateutil


def run(config, working_dir):
    """Main entry point.  Runs the whole pipeline.

    Pass in a config with three methods:
    - get_network() -> Network
    - get_importers(network) -> List[Importer]
    - get_hooks() -> List[Hook]

    Example usage is to write a file, e.g. `magicbeans_local.py` which defines
    your own settings and behavior, and then run the pipeline from that file:

        class LocalConfig:
            def get_network():
                return transfers.Network(...)
            def get_importers(network):
                return [CoinbaseImporter(...), ... ]
            def get_hooks():
                return [my_hook, ... ]

        def my_hook(extracted, _existing_entries=None):
            return  ....  # this will be simpler after factoring filter/map code out of my own local file

        if __name__ == '__main__':
            config = LocalConfig()
            magicbeans.run.run(config)

    TODO: improve  documentation
    TODO: separate in phases, allow running of subphases
    """

    path_directives = os.path.join(working_dir, "10-directives.beancount")
    path_extracted  = os.path.join(working_dir, "20-extracted.beancount")
    path_sorted     = os.path.join(working_dir, "30-extracted-sorted.beancount")
    path_final      = os.path.join(working_dir, "40-final.beancount")

    network = config.get_network()
    default_date = "2000-01-01"

    # Directives
    print(f"==== Generating directives to {path_directives}...")
    with open(path_directives, "w") as out:
        out.write(network.generate_account_directives(default_date))

    # Extract
    print(f"==== Extracting data to {path_extracted}...")
    with open(path_extracted, "w") as out:
        importers = config.get_importers(network)
        hooks = config.get_hooks()
        ingest = beangulp.Ingest(importers, hooks)
        #  Need this to run with --output=<out>
        ingest()

    # Sort
    print(f"==== Sorting extracted data to {path_sorted}...")
    def key(entry):
        return (entry.date, dateutil.parser.parse(entry.meta['timestamp']))
    with open(path_sorted, "w") as out:
        entries, errors, options = parser.parse_file(path_extracted)
        entries.sort(key=key)
        parser.printer.print_entries(entries, file=out)

    # Join files
    print(f"==== Joining directives and sorted data to {path_final}...")
    with open(path_final, "w") as out:
        for path in [path_directives, path_sorted]:
            with open(path) as infile:
                out.write(infile.read())

    print(f"==== Done!  Final file is {path_final}.")


if __name__ == '__main__':
    config = None  # TODO: create some workable default config 
    run(config, "build")