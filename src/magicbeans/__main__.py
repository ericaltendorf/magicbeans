import importlib
import os
from collections import namedtuple

import dateutil
from click import Context
import argparse

import beangulp
from beancount import parser
from beangulp import exceptions, extract, identify, utils
from magicbeans import prices
from magicbeans.config import Config
from magicbeans.prices import PriceFetcher
from magicbeans.reports import default_report

def build_argparser():
    """Build an argument parser for the command line interface."""
    parser = argparse.ArgumentParser(description="Magicbeans Beancount crypto importer & reporter")
    parser.add_argument(
        "-c",
        "--config_py",
        help="Path to the Python file containing the configuration class",
        type=str,
    )
    parser.add_argument(
        "-i",
        "--input_dir",
        nargs="?",
        default="downloads",
        help="Directory containing crypto transaction files to import",
        type=str,
    )
    parser.add_argument(
        "-o",
        "--output_dir",
        nargs="?",
        default="build",
        help="Directory to write intermediate and output files to",
        type=str,
    )
    parser.add_argument(
        "--run-import",
        default=True,
        action="store_true",
        help="Import and aggregate transactions from input_dir",
    )
    parser.add_argument(
        "--no-run-import",
        dest="run_import",
        action="store_false",
        help="Import and aggregate transactions from input_dir",
    )
    parser.add_argument(
        "--run-report",
        default=True,
        action="store_true",
        help="Generate reports from imported transactions",
    )
    parser.add_argument(
        "--no-run-report",
        dest="run_report",
        action="store_false",
    )
    parser.add_argument(
        "--ty-start",
        default=2018,
        help="Tax year to start reporting (inclusive)",
        type=int
    )
    parser.add_argument(
        "--ty-end",
        default=2023,
        help="Tax year to end reporting (inclusive)",
    )

    return parser

def load_config(config_py: str) -> Config:
    """Load the configuration class from the given Python file."""
    if not os.path.exists(config_py):
        raise FileNotFoundError(f"Config file {config_py} does not exist")
    if not os.path.isfile(config_py):
        raise Exception(f"Config file {config_py} is not a file")
    if not config_py.endswith(".py"):
        raise Exception(f"Config file {config_py} is not a Python file")

    spec = importlib.util.spec_from_file_location("local_config", config_py)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "LocalConfig"):
        raise Exception(f"No LocalConfig subclass found in {config_py}")
    else:
        return module.LocalConfig()

def run():
    """Main entry point to run beancount importing and processing.

    Usage: define your own settings and behavior in a subclass of Config.  Pass
    an instance of that subclass to this function, along with the input
    directory containing the crypto transaction files to import, and the
    working directory in which to write intermediate and final output files.
    """

    args = build_argparser().parse_args()
    print(f"Starting up, command line args are {args}")

    input_dir = args.input_dir
    working_dir = args.output_dir
    prices_path = os.path.join(working_dir, "prices.csv")
    price_fetcher = PriceFetcher(prices.Resolution.DAY, prices_path)

    config = load_config(args.config_py)

    # Consider separating into phases to allow running of subphases?
    path_preamble   = os.path.join(working_dir, "00-preamble.beancount")
    path_directives = os.path.join(working_dir, "01-directives.beancount")
    path_extracted  = os.path.join(working_dir, "02-extracted.beancount")
    path_sorted     = os.path.join(working_dir, "03-extracted-sorted.beancount")
    path_final      = os.path.join(working_dir, "04-final.beancount")
    path_report     = os.path.join(working_dir, "05-report.csv")

    print(args.run_import)
    if args.run_import:
        config.set_price_fetcher(price_fetcher)

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
            importers = config.get_importers()
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

        # Save prices
        print(f"==== Saving prices...")
        price_fetcher.write_cache_file()

        print(f"==== Imported transactions to {path_final}.")

    if args.run_report:
        # Run the report
        print(f"==== Running report...")

        numeraire = "USD"  # Should be : config.get_numeraire() ?
        tax_years = range(args.ty_start, args.ty_end + 1)

        default_report.generate(
            tax_years,
            numeraire,
            config.get_covered_currencies(),
            path_final,
            path_report,
        )

        print(f"==== Report complete.")


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
    run()
