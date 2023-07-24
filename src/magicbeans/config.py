# personal data, not to check in

import datetime
from magicbeans import transfers

from beancount.core import account
from beancount.core.data import Transaction

class Config:
    network = transfers.Network([
        transfers.Link("Coinbase", "Bank", "USD"),
        transfers.Link("Coinbase", "GateIO", "USDT"),
        transfers.Link("Coinbase", "Ledger", "BTC"),
        transfers.Link("Coinbase", "Ledger", "ETH"),
        transfers.Link("Coinbase", "Ledger", "LTC"),
        transfers.Link("GateIO", "ChiaWallet", "XCH"),
    ], ["Bank", "Ledger"])

def cbp_filter_entry(entry: Transaction):
    # This is super dumb.  CoinbasePro lists transfers from Coinbase
    # as deposits, but Coinbase doens't list the outgoing transfers.
    # Filter those incoming ones.  TODO: move this into some user-
    # specific postprocessing step.  TODO: use IDs in metadata.
    if (entry.date, entry.narration) in [
        (datetime.date(2020, 2, 17), "CBP: Deposit USD"),
        (datetime.date(2020, 2, 18), "CBP: Deposit BTC"),
        (datetime.date(2020, 2, 18), "CBP: Deposit ETH"),
        (datetime.date(2020, 2, 24), "CBP: Deposit LTC"),
    ]:
        return True
    
    # This is also super dumb.  CoinbasePro has these five transfers
    # as dupes of ones in Coinbase.
    # if (entry.date, entry.meta['transferid']) in [
    #     (datetime.date(2021, 8, 30), "d2d21952-90e5-452a-bba7-e9ca0dc89108"),
    #     (datetime.date(2021, 8, 30), "1736d6a5-db82-4275-9ba6-dc76376dd95b"),
    #     (datetime.date(2021, 8, 30), "75c4085c-e078-4903-aecc-04708a2eed1d"),
    #     (datetime.date(2021, 9, 3), "6949a88e-0459-4dcc-9669-c8c6b44faec2"),
    #     (datetime.date(2021, 9, 3), "79048ec2-ab3f-4c59-9997-ff89e4199b4c"),
    # ]:
    #     return True

    return False

# TODO: remove
def get_network():
    return Config.network

def cb_compute_remote_account(currency: str):
    return get_network().target(f"Assets:Coinbase:{currency}", currency)
    # USDT transactions were to GateIO; others were to a wallet
    # TODO: move this business logic out of the common library
    remote_account = account.join("Assets:Wallet", currency)
    if currency == "USDT":
        remote_account = "Assets:GateIO:USDT"
    elif currency == "USD":
        remote_account = "Assets:Bank:USD"
    return remote_account
    
def cbp_compute_remote_account(currency: str):
    return get_network().target(f"Assets:Coinbase:{currency}", currency)
    # USDT transactions were to GateIO; others were to a wallet
    # TODO: move this business logic out of the common library
    remote_account = account.join("Assets:Wallet", currency)
    if currency == "USDT":
        remote_account = "Assets:GateIO:USDT"
    elif currency == "USD":
        remote_account = "Assets:Bank:USD"
    return remote_account

def gio_compute_remote_account(currency: str):
    return get_network().target(f"Assets:GateIO:{currency}", currency)
    # USDT transactions were to Coinbase; others were to a wallet
    # TODO: move this business logic out of the common library
    remote_account = account.join("Assets:Wallet", currency)
    if currency == "USDT":
        remote_account = "Assets:Coinbase:USDT"
    return remote_account