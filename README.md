# magicbeans
Cryptocurrency tax and tracking tools for the Beancount platform.

## Goals:
- Accurate importing of crypto transactions from exchanges or wallet software
- Accurate and traceable capital gains/loss tracking and computation
- Handle mining/staking/farming income
- Tax optimization options beyond HIFO/FIFO
- Flexibility between automatic and manual lot selection
- Scale to hundreds or thousands of transactions and cost-basis lots
- Generation of reports suitable for preparing (US) taxes

Currently out of scope are importers that extract directly from blockchain data
using crypto addresses.

This is not standalone software, it consists of modules, extensions, and tools
that operate on the Beancount platform.  For more information see:
https://github.com/beancount

## Status

As of now (2023.08.04) this package is not runnable by anyone other than the author.
See TODOs below.

Data importers which have been (mostly) implemented include:
- Coinbase csv
- CoinbasePro csv
- Gate.IO csv
- [Chia](http://www.chia.net/) reference wallet

## TODO

### Enable collaborators & alpha testers
- Set up a standard method of running the code, including adding a preamble of options and account declarations (currently `build.sh` outside this repo)
- Set up a config framework for local/private stuff (account info, specific transaction overrides)
- Integrate the Chia wallet preprocessing code into this repository
- Write some introductory documentation
- Write some more detailed documentation with tips, tricks, gotchas, examples, and war stories of real-life data
- clean up license declarations

### Necessary and missing functionality
- Get prices working (see [thread](https://groups.google.com/g/beancount/c/8LS1e2GfAmk),
  maybe Integrate [beancount-coinmarketcap](https://github.com/aamerabbas/beancount-coinmarketcap) plugin)
- Ensure prices and acquisition dates are being tracked through transfers
- Figure out plan for identifying, applying, saving, and applying in the future, booking decisions.
  Ref: [minimizegains](https://github.com/redstreet/fava_investor/tree/main/fava_investor/modules/minimizegains)
  and [match_trades](https://github.com/beancount/beanlabs/blob/master/beanlabs/trades/match_trades.py)
- Classify short/long term gains (ref:
  [plugin](https://github.com/redstreet/beancount_reds_plugins/tree/main/beancount_reds_plugins/capital_gains_classifier))

### Cleanup
- Make all importers fill out narration field with a human readable description of the transaction, with amounts and ID when possible (helps a lot when inspecting with bean-query)
- Get importer tests working with run script etc
- Set up continuous integration w/ typechecking and unit tests
- Create a canonical way to automatically apply registered fix-ups on imported data
- Address TODOs throughout code
- Get zerosum plugin working, report these and other errors somewhere in the build pipeline