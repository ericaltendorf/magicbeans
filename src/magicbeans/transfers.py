"""Utilities for managing transfers among a network of accounts."""

from typing import List, Set
from typing import NamedTuple

from beancount.core import account

class Link(NamedTuple):
    """A link between two institutions, in a given currency.  Asset account names
    will be constructed from instution names, so don't prefix "Assets:" """
    institution_a: str
    institution_b: str
    currency: str

class Network():
    """A network of accounts and links, for reasoning about asset transfers.
    
    A network is defined by a set of accounts (vertices) and links between
    them that represent a conduit for transfers in a particular currency.  Once
    defined, the network can be queried to infer the source or destination of
    a particular transfer, given only information about one leg.  For example,
    suppose you use Coinbase and Ledger for BTC, and GateIO and Chia Wallet for
    XCH, and you fund Coinbase with USD from your bank, and transfer USDT to
    GateIO.  Your network is:
    
    (Bank)
       |
      USD
       |
    (Coinbase) ---BTC--- (Ledger Wallet)
       |
      USDT
       |
    (GateIO) ---XCH--- (Chia Wallet)

    Once defined, the network can answer, for example:
    - If USDT arrives in GateIO, it must have come from Coinbase 
    - If Ledger Wallet sends BTC, it must have gone to Coinbase

    This, of course, assumes that the network is well defined, that currencies
    uniquely define the transfer conduits, and that there are no other out of
    band transfers.
    """

    def __init__(self, links: List[Link], untracked_institutions: List[str] = None):
        """Constructs a routing network with zero sum transfer account buffers.
           Assumes accounts have the form "Assets:<Institution>:<Currency> ."""
        # Sanity check
        if untracked_institutions:
            all_linked_institutions = set([l.institution_a for l in links] +
                                          [l.institution_b for l in links])
            if not set(untracked_institutions).issubset(all_linked_institutions):
                raise Exception(f"Untracked ({untracked_institutions}) included "
                                f"institutions not in links ({links})")
        else:
            untracked_institutions = []

        self.links = links
        self.fwd_routes = {}
        self.rev_routes = {}
        self.regular_accts = set()
        self.buffer_accts = []
        for link in links:
            account_a = account.join("Assets", link.institution_a, link.currency)
            account_b = account.join("Assets", link.institution_b, link.currency)

            self.regular_accts.add(account_a)
            self.regular_accts.add(account_b)

            if link.institution_a in untracked_institutions or link.institution_b in untracked_institutions:
                self._add_fwd_route(account_a, link.currency, account_b)
                self._add_fwd_route(account_b, link.currency, account_a)
                self._add_rev_route(account_a, link.currency, account_b)
                self._add_rev_route(account_b, link.currency, account_a)

            else:
                a2b_buffer = account.join("Assets", "ZeroSumAccount",
                                        f"{link.institution_a}-To-{link.institution_b}",
                                        link.currency)
                b2a_buffer = account.join("Assets", "ZeroSumAccount",
                                        f"{link.institution_b}-To-{link.institution_a}",
                                        link.currency)

                self.buffer_accts.append(a2b_buffer)
                self.buffer_accts.append(b2a_buffer)

                self._add_fwd_route(account_a, link.currency, a2b_buffer)
                self._add_fwd_route(account_b, link.currency, b2a_buffer)
                self._add_rev_route(account_a, link.currency, b2a_buffer)
                self._add_rev_route(account_b, link.currency, a2b_buffer)

    def __str__(self):
        return "\n".join(f"{a} {b} -> {c}" for (a, b), c in self.fwd_routes.items())

    def _add_fwd_route(self, source, currency, target):
        key = (source, currency)
        if key in self.fwd_routes:
            raise Exception(f"Route already exists for {key}")
        self.fwd_routes[key] = target

    def _add_rev_route(self, source, currency, target):
        key = (source, currency)
        if key in self.rev_routes:
            raise Exception(f"Route already exists for {key}")
        self.rev_routes[key] = target

    def target(self, account: str, currency: str) -> str:
        """From this account, where do transfers in this currency go?"""
        return self.fwd_routes[(account, currency)]

    def source(self, account: str, currency: str) -> str:
        """For this account, where did transfers in this currency come from?"""
        return self.rev_routes[(account, currency)]

    def route(self, is_outgoing: bool, account: str, currency: str) -> str:
        if is_outgoing:
            return self.target(account, currency)
        else:
            return self.source(account, currency)

    def buffer_accounts(self):
        return self.buffer_accts

    def generate_account_directives(self, opening_date: str) -> str:
        directives = []
        for acct in self.regular_accts:
            directives.append(f"{opening_date} open {acct}")        
        for acct in self.buffer_accts:
            directives.append(f"{opening_date} open {acct}")
        directives.sort()
        return "\n".join(directives) + "\n"