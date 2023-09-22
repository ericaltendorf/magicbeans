# magicbeans
Cryptocurrency tax tracking and reporting tools for the Beancount platform.

An example report: [data/magicbeans_example.pdf](data/magicbeans_example.pdf)

## Goals:
- Accurate importing of crypto transactions from exchanges or wallet software
- Accurate and traceable capital gains/loss tracking and computation
- Handle mining/staking/farming income
- Handle taxable asset exchanges (e.g., USDT for BTC)
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

Magicbeans works for the very narrow set of data on which I've personally
used it.  It will almost certainly break when exercised on new situations.
It is full of TODO's and known issues which need shaking out.  I would
appreciate alpha testers who are willing to do some debugging, testing,
and fixing.

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
- Verify that price and acquisition date tracking transfers is working ([background](https://github.com/beancount/beancount/issues/614))
- Write tax-minimizing booking algo
  Ref: [minimizegains](https://github.com/redstreet/fava_investor/tree/main/fava_investor/modules/minimizegains)
  and [match_trades](https://github.com/beancount/beanlabs/blob/master/beanlabs/trades/match_trades.py)
- Figure out plan for saving booking decisions and applying in the future

### Cleanup
- Existing price fetcher isn't ideal, see if we can get higher-resolution historical data, and 
  corroborate across multiple sources
- Set up continuous integration w/ typechecking and unit tests
- Use `@dataclass` where appropriate
- Make a clear decision on the use of terms "Buy", "Sell", and "Swap"
- Create a canonical way to automatically apply registered fix-ups on imported data
- Address TODOs throughout code
- Get zerosum plugin working, report these and other errors somewhere in the build pipeline
- Use `filter_txns()` throughout rather than `filter()` with `isinstance()`
