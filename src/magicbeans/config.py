from typing import List
from beangulp.importer import Importer
from magicbeans import prices, transfers

class Config:
    """The API for magicbeans to access local configuration settings.
    
    You should subclass this, implement the necessary methods, and pass an
    instance of your subclass to the `run` function in `magicbeans.run`."""

    def get_network(self) -> transfers.Network:
        """Return the transfer network to use."""
        raise NotImplementedError
        
    def get_importers(self) -> List[Importer]:
        """Return the list of beancount importers to use."""
        raise NotImplementedError

    def get_hooks(self):  # TODO: type hint
        """Return the list of hooks to use.

        Hooks are functions which take a list of extracted entries and
        optionally a list of existing entries, and return a list of
        entries."""
        raise NotImplementedError

    def get_preamble(self) -> str:
        """Return the preamble (opening beancount directives and entries) to use.
        
        This is often just a static hard-coded string."""
        raise NotImplementedError

    def get_price_fetcher(self) -> prices.PriceFetcher:
        """Return the price fetcher to use."""
        raise NotImplementedError
    
    def is_like_operating_currency(self, currency: str) -> bool:
        """Return True if spending/receiving this is anaalogous to buying/selling.
        
        E.g., is this   an operating currency or a stablecoin pegged to one.
        This can be used to mark transactions which are nominally a "buy" or
        "sell"."""
        return currency in ["USD", "USDC", "USDT"]

    def get_covered_currencies(self) -> List[str]:
        """Return a list of cryptocurrencies on which we'll report."""
        return ["BTC", "ETH", "LTC", "XCH"]