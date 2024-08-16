# magicbeans
Cryptocurrency tax tracking and reporting tools for the Beancount platform.

An example generated report: [data/magicbeans_example.pdf](data/magicbeans_example.pdf)

## Overview

Goals:
- Accurate importing of crypto transactions from exchanges or wallet software
- Accurate and traceable capital gains/loss tracking and computation
- Handle mining/staking/farming income
- Handle taxable asset exchanges (e.g., USDT for BTC)
- Tax optimization options beyond HIFO/FIFO
- Flexibility between automatic and manual lot selection
- Scale to hundreds or thousands of transactions and cost-basis lots
- Generation of reports suitable for preparing (US) taxes

Magicbeans is not standalone software, it consists of modules, extensions, and tools
that operate on the Beancount platform.  For more information see:
https://github.com/beancount .

No warranty is expressed or implied; in fact I can almost guarantee you that
Magicbeans behaves incorrectly in many situations.


## Status

Magicbeans currently can:
- Import crypto activity data from a few sources (Coinbase csvs, CoinbasePro
csvs, Gate.IO csvs, and the [Chia](http://www.chia.net/) default wallet) into
Beancount format (and transaction semantics)
- Run standard Beancount functionality, including balancing transactions,
flagging discrepencies, cost-basis lot tracking, computing capital gains
- Generate PDF reports containing high-level summaries of capital gains
(similar to IRS 8949) and income, as well as very detailed reports tracking
individual lots from acquisition through inventory through disposition, to 
enable auditing

However, Magicbeans is underexercised and undertested.  It is badly in need
of more beta-testers/developers who are willing to try to use it with their
data, debug where it breaks, and contribute fixes.

## Installation and Usage

*Reminder: This package is underdeveloped and undertested.*  Please download
and use only if you're ready to do a developer's install (i.e., you're familiar
with git, python virtual environments, pip, etc.), and to tweak a bunch of stuff,
check the output carefully, and assist at least by filing issues for
problems found.

The following are installation instructions for Linux/Ubuntu.  For other
platforms, you may need to adjust some commands and paths.  Also, if you
plan to contribute back to Magicbeans, you should first fork the git repo,
and then clone your own fork instead.

Find a nice empty working directory:
```
  mkdir crypto-taxes
  cd crypto-taxes
```

Clone magicbeans (note: if you plan to contribute, you'll want to first fork it
and then clone your fork with ssh):
```
  git clone https://github.com/ericaltendorf/magicbeans.git
```

Create and enter a venv, and install (in -e "editable" mode, so you can tweak):
```
  python3 -m venv venv-magicbeans
  source venv-magicbeans/bin/activate
  venv-magicbeans/bin/pip install -e magicbeans
```

Install system utilities/libraries:
```
  sudo apt install latexmk texlive texlive-latex-extra
```

Create directories for your input files (e.g. csv files of transactions)
and a working directory for Magicbeans to write output (and temporary) files:
```
  mkdir downloads build
  # put stuff in downloads
```

Next you need to configure your workflow (your accounts, importers,
transformations, hooks, etc.).  This is done with Python code which implements
the Magicbeans `Config` class.  An example is provided in `config_example.py`.
Since your config may end up including personal account information, you should
copy the example script to a private repo to version-control it privately.

Now you should be ready to run Magicbeans.  To see the command line options:

```
  python3 -m magicbeans -h
```

You will need to specify arguments to point Magicbeans to your config python
code, your input and output directories, etc.


## TODO

### Enable collaborators & alpha testers
- Document how to run report generator (see also cleanup task below)
- Write some more detailed documentation with tips, tricks, gotchas, examples, and war stories of real-life data

### Necessary and missing functionality
- Verify that price and acquisition date tracking transfers is working ([background](https://github.com/beancount/beancount/issues/614))
- Write tax-minimizing booking algo
  Ref: [minimizegains](https://github.com/redstreet/fava_investor/tree/main/fava_investor/modules/minimizegains)
  and [match_trades](https://github.com/beancount/beanlabs/blob/master/beanlabs/trades/match_trades.py)
- Figure out plan for saving booking decisions and applying in the future

### Cleanup
- Integrate runner.py and run_report.py into one script
- Existing price fetcher isn't ideal, see if we can get higher-resolution historical data, and 
  corroborate across multiple sources
- Set up continuous integration w/ typechecking and unit tests
- Use `@dataclass` where appropriate
- Make a clear decision on the use of terms "Buy", "Sell", and "Swap"
- Create a canonical way to automatically apply registered fix-ups on imported data
- Address TODOs throughout code
- Get zerosum plugin working, report these and other errors somewhere in the build pipeline
- Use `filter_txns()` throughout rather than `filter()` with `isinstance()`
