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

This code should be runnable, but you would need some guidance.  If you end up
here and want to try it, contact me and I'll prioritize documentation (see
below).

Data importers which have been (mostly) implemented include:
- Coinbase csv
- CoinbasePro csv
- Gate.IO csv
- [Chia](http://www.chia.net/) default wallet

## TODO

### Enable collaborators & alpha testers
- Write some introductory documentation
- Document requirements (pip packages, and beancount plugins)
- Write some more detailed documentation with tips, tricks, gotchas, examples, and war stories of real-life data

### Necessary and missing functionality
- Add option for folding trading fees into cost basis and proceeds
- Ensure prices and acquisition dates are being tracked through transfers (they might be?)
- Figure out plan for identifying, applying, saving, and applying in the future, booking decisions.
  Ref: [minimizegains](https://github.com/redstreet/fava_investor/tree/main/fava_investor/modules/minimizegains)
  and [match_trades](https://github.com/beancount/beanlabs/blob/master/beanlabs/trades/match_trades.py)

### Cleanup
- Existing price fetcher isn't ideal, see if we can get higher-resolution historical data, and 
  corroborate across multiple sources
- Make all importers fill out narration field with a human readable description of the transaction, with amounts and ID when possible (helps a lot when inspecting with bean-query)
- Set up continuous integration w/ typechecking and unit tests
- Create a canonical way to automatically apply registered fix-ups on imported data
- Address TODOs throughout code
- Get zerosum plugin working, report these and other errors somewhere in the build pipeline