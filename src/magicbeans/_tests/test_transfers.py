import sys

import pytest

from magicbeans.transfers import Network, Link

def test_network() -> None:
    net = Network([
        Link("Coinbase", "Bank", "USD"),
        Link("Coinbase", "Wallet", "BTC"),
    ])

    assert (net.target("Assets:Coinbase:USD", "USD") ==
            "Assets:Xfer:Coinbase-Bank:USD")
    assert (net.target("Assets:Coinbase:BTC", "BTC") ==
            "Assets:Xfer:Coinbase-Wallet:BTC")
    assert (net.source("Assets:Coinbase:USD", "USD") ==
            "Assets:Xfer:Bank-Coinbase:USD")
    assert (net.source("Assets:Coinbase:BTC", "BTC") ==
            "Assets:Xfer:Wallet-Coinbase:BTC")

def test_route() -> None:
    net = Network([
        Link("Coinbase", "Bank", "USD"),
        Link("Coinbase", "Wallet", "BTC"),
    ])

    assert (net.route(True, "Assets:Coinbase:USD", "USD") ==
            "Assets:Xfer:Coinbase-Bank:USD")
    assert (net.route(False, "Assets:Coinbase:USD", "USD") ==
            "Assets:Xfer:Bank-Coinbase:USD")

def test_network_with_untracked() -> None:
    net = Network([
        Link("Coinbase", "Bank", "USD"),
        Link("Coinbase", "Wallet", "BTC"),
        Link("Coinbase", "Wallet", "ETH"),
    ], ["Wallet"])

    assert (net.target("Assets:Coinbase:USD", "USD") ==
            "Assets:Xfer:Coinbase-Bank:USD")
    assert (net.target("Assets:Coinbase:BTC", "BTC") ==
            "Assets:Wallet:BTC")
    assert (net.target("Assets:Coinbase:ETH", "ETH") ==
            "Assets:Wallet:ETH")
    assert (net.source("Assets:Coinbase:USD", "USD") ==
            "Assets:Xfer:Bank-Coinbase:USD")
    assert (net.source("Assets:Coinbase:BTC", "BTC") ==
            "Assets:Wallet:BTC")
    assert (net.source("Assets:Coinbase:ETH", "ETH") ==
            "Assets:Wallet:ETH")

def test_generate_account_directives() -> None:
    net = Network([
        Link("Coinbase", "Bank", "USD"),
        Link("Coinbase", "Wallet", "BTC"),
        Link("Coinbase", "Wallet", "ETH"),
    ], ["Bank"])

    expected = (
        "2000-01-01 open Assets:Bank:USD\n"
        "2000-01-01 open Assets:Coinbase:BTC\n"
        "2000-01-01 open Assets:Coinbase:ETH\n"
        "2000-01-01 open Assets:Coinbase:USD\n"
        "2000-01-01 open Assets:Wallet:BTC\n"
        "2000-01-01 open Assets:Wallet:ETH\n"
        "2000-01-01 open Assets:Xfer:Coinbase-Wallet:BTC\n"
        "2000-01-01 open Assets:Xfer:Coinbase-Wallet:ETH\n"
        "2000-01-01 open Assets:Xfer:Wallet-Coinbase:BTC\n"
        "2000-01-01 open Assets:Xfer:Wallet-Coinbase:ETH\n"
    )

    assert net.generate_account_directives("2000-01-01") == expected