import datetime
from decimal import Decimal
from magicbeans import prices, transfers
from magicbeans.config import Config
from magicbeans.importers.chiawallet import ChiaWalletImporter
from magicbeans.importers.coinbasepro import CoinbaseProImporter
from magicbeans.importers.gateio import GateIOImporter

# TODO: this is just code -- is there a pytest mocking framework we should be using?

# TODO: each of these testing importers uses a different set of accounts -- clean up

def gateio_importer_for_testing():
    """Returns an instance of this importer for testing."""
    return GateIOImporter(
        account_root="Assets:GateIO",
        account_pnl="Income:PnL",
        account_fees="Expenses:Financial:Fees",
        config=MockConfig())

def chia_wallet_importer_for_testing():
    """Returns an instance of this importer for testing."""
    return ChiaWalletImporter(
        account_root="Assets:ChiaWallet",
        account_mining_income="Income:Mining",
        account_gains="Income:PnL",
        account_fees="Expenses:Fees",
        network=MockConfig().get_network(),
        config=MockConfig(),

        # TODO: exercise more of these configurations in the test
        chiawallet_config_dict={
            "farming_reward_addrs": ["xch2farming", "xch2pooladdr"],
            "known_farming_reward_txs": [],
            "blocklisted_txs": [],
            "allowed_tokens": ["XCH"],
            "ignored_tokens": ["Chia Holiday 2021 Token"],
            }
    )

def coinbasepro_importer_for_testing():
    return CoinbaseProImporter(
        account_root="Assets:Coinbase",
        account_pnl="Income:PnL",
        account_fees="Expenses:Fees",
        network=MockConfig().get_network(),
        config=MockConfig(),
    )

# TODO: mocks for other importer configs

class MockPriceFetcher():
    def get_price(self, currency: str, timestamp: datetime.datetime) -> Decimal:
        if currency == "USDT":
            return Decimal("1.0001")
        elif currency == "XCH":
            return Decimal("50.0")
        elif currency == "BTC":
            return Decimal("25000.0")
        elif currency == "ETH":
            return Decimal("1000.0")
        else:
            raise ValueError(f"Unknown currency {currency}")

class MockConfig(Config):
    def __init__(self) -> None:
        super().__init__()
        self.price_fetcher = MockPriceFetcher()

    def get_network(self):
        return transfers.Network([transfers.Link("GateIO", "Coinbase", "USDT"),
                                  transfers.Link("GateIO", "ChiaWallet", "XCH"),
                                  transfers.Link("Coinbase", "Bank", "USD"),
                                  transfers.Link("Coinbase", "Ledger", "BTC"),
                                  ],
                                 untracked_institutions=["Bank", "Ledger"])  # not particularly relevant

    def get_price_fetcher(self) -> prices.PriceFetcher:
        return self.price_fetcher