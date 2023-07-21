"""Utilities for managing transfers among a network of accounts."""

from typing import List
from typing import NamedTuple

from beancount.core import account

class Link(NamedTuple):
    institution_a: str
    institution_b: str
    currency: str

# TODO: consider special handling for untracked leaf node accounts; those don't
# need a zero sum buffer account in between.
class Network():
    def __init__(self, links: List[Link]):
        """Constructs a routing network with zero sum transfer account buffers.
           Assumes accounts have the form "Assets:<Institution>:<Currency> ."""
        self.links = links
        self.fwd_routes = {}
        self.rev_routes = {}
        self.buffer_accts = []
        for link in links:
            account_a = account.join("Assets", link.institution_a, link.currency)
            account_b = account.join("Assets", link.institution_b, link.currency)
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

    def route(self, account: str, currency: str) -> str:
        """From this account, where do transfers in this currency go?"""
        return self.fwd_routes[(account, currency)]

    def source(self, account: str, currency: str) -> str:
        """For this account, where did transfers in this currency come from?"""
        return self.rev_routes[(account, currency)]

    def buffer_accounts(self):
        return self.buffer_accts