import sys

import pytest

from bean_crypto_import.transfers import Network, Link

def test_network() -> None:
    net = Network([
        Link("Coinbase", "Bank", "USD"),
        Link("Coinbase", "Wallet", "BTC"),
    ])

    assert (net.route("Assets:Coinbase:USD", "USD") ==
            "Assets:ZeroSumAccount:Coinbase-To-Bank:USD")
    assert (net.route("Assets:Coinbase:BTC", "BTC") ==
            "Assets:ZeroSumAccount:Coinbase-To-Wallet:BTC")
    assert (net.source("Assets:Coinbase:USD", "USD") ==
            "Assets:ZeroSumAccount:Bank-To-Coinbase:USD")
    assert (net.source("Assets:Coinbase:BTC", "BTC") ==
            "Assets:ZeroSumAccount:Wallet-To-Coinbase:BTC")

def test_network_with_untracked() -> None:
    net = Network([
        Link("Coinbase", "Bank", "USD"),
        Link("Coinbase", "Wallet", "BTC"),
        Link("Coinbase", "Wallet", "ETH"),
    ], ["Wallet"])

    assert (net.route("Assets:Coinbase:USD", "USD") ==
            "Assets:ZeroSumAccount:Coinbase-To-Bank:USD")
    assert (net.route("Assets:Coinbase:BTC", "BTC") ==
            "Assets:Wallet:BTC")
    assert (net.route("Assets:Coinbase:ETH", "ETH") ==
            "Assets:Wallet:ETH")
    assert (net.source("Assets:Coinbase:USD", "USD") ==
            "Assets:ZeroSumAccount:Bank-To-Coinbase:USD")
    assert (net.source("Assets:Coinbase:BTC", "BTC") ==
            "Assets:Wallet:BTC")
    assert (net.source("Assets:Coinbase:ETH", "ETH") ==
            "Assets:Wallet:ETH")

