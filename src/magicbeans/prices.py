"""Fetch prices for magicbeans importers.

To calculate capital gains and losses, we need to establish prices (value w.r.t.
the native currency) at the point of each transaction.  Transactions reported
by exchanges between tokens and USD generally imply price already, but swaps
(e.g., BTC for USDT) and wallet transactions need to be augmented with prices.

Although beancount provides a utility for fetching prices (bean-price), it:
- does not appear to fetch prices for the cases we require
- only gives daily prices, which is perhaps OK, but not ideal

This library provides an intentionally minimal method for magicbeans to fetch
prices.  It should not grow into a full-featured price-fetching library without
coordination with the direction of bean-price development.

All datetimes and timestamps must be in UTC.
"""

import csv
import datetime
from decimal import Decimal
from enum import Enum
from string import Template
import time
from typing import NamedTuple
import pytz

import requests

class DataSource(Enum):
    CRYPTOCOMPARE = 1
    COINCODEX = 2

SELECTED_DATASOURCE = DataSource.COINCODEX

class Resolution(Enum):
    DAY = 1
    HOUR = 2
    MINUTE = 3  # service only offers hour resolution anyway
    SECOND = 4  # service only offers hour resolution anyway

class CacheEntry(NamedTuple):
    timestamp: datetime.datetime
    currency: str
    high: Decimal
    low: Decimal

    # TODO: enforce timestamps are UTC

    # TODO: rounding the price is useful but should probably be done in a more
    # principled or transparent way.

    def price(self) -> Decimal:
        return round((self.high + self.low) / Decimal("2.0"), 4)

class PriceFetcher:
    """Fetch prices for magicbeans importers.
    
    When a price is requested, it will first be checked against an in-memory cache,
    which is indexed at the provided time resolution.  If not found, it will be requested
    from an external source and added to the in-memory cache.

    The in-memory cache is populated from a file upon initialization.  If you wish to
    persist newly aquired obtained prices you must call write_cache_file()
    before destroying this object.  The file contains full resolution
    timestamps, so the same file can be loaded at different resolutions.
    """

    def __init__(self, resolution: Resolution, price_file: str) -> None:
        self.res = resolution
        self.cache_path = price_file
        self.cache = {}

        # For throttling API calls.
        self.last_fetch_ts = datetime.datetime.min
        self.min_fetch_interval_ms = 15000

        self.build_cache_from_file()

    def build_cache_from_file(self) -> None:
        """Build the cache file."""
        try:
            with open(self.cache_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = datetime.datetime.fromisoformat(row["timestamp"])
                    currency = row["currency"]
                    high = Decimal(row["high"])
                    low = Decimal(row["low"])
                    self.cache[self._cache_key(ts, currency)] = CacheEntry(ts, currency, high, low)
        except FileNotFoundError:
            print("No price cache file found.  One will be created.")

    def write_cache_file(self) -> None:
        """Write the cache file to disk."""
        with open(self.cache_path, "w") as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp", "currency", "high", "low"])
            writer.writeheader()
            for ts, currency, high, low in self.cache.values():
                writer.writerow({
                    "timestamp": ts.isoformat(),
                    "currency": currency,
                    "high": high,
                    "low": low,
                })

    def get_price(self, currency: str, ts: datetime.datetime) -> Decimal:
        """Return the price of the currency at the timestamp, up to the cache resolution."""

        if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
            raise Exception(f"Timestamp not timezone aware; must be UTC.  Was: {ts}")
        if ts.tzinfo != pytz.utc: # datetime.timezone.utc:
            raise Exception(f"Timestamp not UTC.  Was: {ts} , timzone {ts.tzinfo}")

        key = self._cache_key(ts, currency)

        if not key in self.cache:
            self._fetch_price_from_source(currency, ts)

        if key in self.cache:
            return self.cache[key].price()
        else:
            raise ValueError("Price not found in cache after fetching")

    def _quantize_timestamp(self, ts: datetime.datetime) -> datetime.datetime:
        if self.res == Resolution.SECOND:
            return ts.replace(microsecond=0)
        elif self.res == Resolution.MINUTE:
            return ts.replace(second=0, microsecond=0)
        elif self.res == Resolution.HOUR:
            return ts.replace(minute=0, second=0, microsecond=0) 
        elif self.res == Resolution.DAY:
            return ts.replace(hour=0, minute=0, second=0, microsecond=0) 
        else:
            raise ValueError("Invalid resolution")

    def _cache_key(self, ts: datetime.datetime, currency: str) -> str:
        """Return the cache key for the given timestamp and currency."""
        return "{}-{}".format(self._quantize_timestamp(ts).isoformat(), currency)

    def _fetch_price_from_source(self, currency: str, ts: datetime.datetime):
        """Fetch the price of the currency at the timestamp from an external source."""
        if not ts:
            raise ValueError("Timestamp required")

        print(f"Price fetch: {currency} {ts} ", end="")
        s_since_last_call = (datetime.datetime.now() - self.last_fetch_ts).total_seconds()
        throttle_deficit_s = self.min_fetch_interval_ms / 1000 - s_since_last_call
        if throttle_deficit_s > 0:
            print(f"throttling API call: {throttle_deficit_s:.3f} seconds")
            time.sleep(throttle_deficit_s)
        else:
            print()
        self.last_fetch_ts = datetime.datetime.now()

        if SELECTED_DATASOURCE == DataSource.CRYPTOCOMPARE:
            # This soure lacks early price data for XCH, and also has limited resolution for
            # historical data -- although it claims to be hourly, it appears to be daily.
            # See https://min-api.cryptocompare.com/documentation
            # TODO: USD is hard-coded here.
            api_url_template = "https://min-api.cryptocompare.com/data/v2/histohour?fsym={currency}&toTs={ts}&tsym=USD&limit=1"
            url = api_url_template.format(currency=currency, ts=int(ts.timestamp()))
        elif SELECTED_DATASOURCE == DataSource.COINCODEX:
            api_url_template = "https://coincodex.com/api/coincodex/get_coin_history/{currency}/{start_date}/{end_date}/{samples}"
            url = api_url_template.format(currency=currency, start_date=ts.date().isoformat(), end_date=ts.date().isoformat(), samples=1)
        else:
            raise Exception("Invalid data source")

        response = requests.get(url)
        if response.status_code != 200:
            raise ValueError(f"HTTP response {response.status_code}\n"
                             f"request was {url}")
        json = response.json()

        if SELECTED_DATASOURCE == DataSource.CRYPTOCOMPARE:
            if json["Response"] != "Success":
                raise ValueError(f"API call failed with message {json['Message']}\n"
                                f"request was {url}")
            for record in json.get("Data", {}).get("Data", []):
                ts = datetime.datetime.fromtimestamp(record["time"], tz=datetime.timezone.utc)
                high = Decimal(record["high"])
                low = Decimal(record["low"])
                self.cache[self._cache_key(ts, currency)] = CacheEntry(ts, currency, high, low)
        elif SELECTED_DATASOURCE == DataSource.COINCODEX:
            for (price_ts, price, _volume, _undocumented_value) in json.get(currency, {}):
                ts = datetime.datetime.fromtimestamp(price_ts, tz=datetime.timezone.utc)
                price_decimal = Decimal(price)
                self.cache[self._cache_key(ts, currency)] = CacheEntry(ts, currency, price_decimal, price_decimal)
        else:
            raise Exception("Invalid data source")

        
if __name__ == "__main__":
    pf = PriceFetcher(Resolution.MINUTE, "prices.csv")
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    print(pf.get_price("BTC", now))
    pf.write_cache_file()