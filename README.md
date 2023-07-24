# magicbeans
Beancount importers for crypto data.

For context, see:
- https://github.com/beancount/beancount
- https://github.com/beancount/beangulp

## TODO
- Set up continuous integration w/ typechecking and unit tests
- Integrate [beancount-coinmarketcap](https://github.com/aamerabbas/beancount-coinmarketcap) plugin for prices
- Create a canonical way to automatically apply registered fix-ups on imported data
- Create a canonical way to apply a set of fixed booking decisions to imported data
- Set up a config framework for local/private stuff (account info, specific transaction overrides)
- Get zerosum plugin working, if needed
- Integrate the Chia wallet preprocessing code into this repository
- Address TODOs throughout code
- Deal with non-USD transaction fees within-transaction correctly (see gateio importer)
- Set up a standard method of running the code, including adding a preamble of options and account declarations (currently `build.sh`` outside this repo)
- Figure out how to report transactions and bookings after checking validity
- Figure out how to report bookings in an automated form that can be fed back in as fixed bookings on the next run