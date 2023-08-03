# magicbeans
Cryptocurrency tax and tracking tools for the Beancount platform.

Goals:
- Accurate importing of crypto transactions from exchanges or hardware wallets
- Accurate and tracable PnL / capital gains/loss tracking and computation
- Tax optimization options beyond HIFO/FIFO
- Generation of reports suitable for preparins (US) taxes

This is not standalone software, it consists of modules, extensions, and tools
that operate on the Beancount platform.  For more information see:
- https://github.com/beancount

Especially:
- https://github.com/beancount/beancount
- https://github.com/beancount/beangulp
- https://github.com/beancount/beanquery

## TODO
- Write some introductory documentation
- Write some more detailed documentation with tips, tricks, gotchas, examples, and war stories of real-life data
- Make all importers fill out narration field with a human readable description of the transaction, with amounts and ID when possible (helps a lot when inspecting with bean-query)
- Set up continuous integration w/ typechecking and unit tests
- Integrate [beancount-coinmarketcap](https://github.com/aamerabbas/beancount-coinmarketcap) plugin for prices
- Create a canonical way to automatically apply registered fix-ups on imported data
- check out https://github.com/redstreet/beancount_reds_plugins/tree/main/beancount_reds_plugins/capital_gains_classifier
- Create a canonical way to apply a set of fixed booking decisions to imported data, or look into https://github.com/redstreet/fava_investor/tree/main/fava_investor/modules/minimizegains or https://github.com/beancount/beanlabs/blob/master/beanlabs/trades/match_trades.py
- Set up a config framework for local/private stuff (account info, specific transaction overrides)
- Get zerosum plugin working, if needed
- Integrate the Chia wallet preprocessing code into this repository
- Address TODOs throughout code
- Deal with non-USD transaction fees within-transaction correctly (see gateio importer)
- Set up a standard method of running the code, including adding a preamble of options and account declarations (currently `build.sh`` outside this repo)
- Figure out how to report transactions and bookings after checking validity
- Figure out how to report bookings in an automated form that can be fed back in as fixed bookings on the next run

## Currently out of scope
- Importers that extract directly from blockchain data using crypto addresses