"""Importer for transactions from a Chia wallet (https://www.chia.net/).

Reads a CSV of Chia reference wallet "transactions", of format:
  token_name,transaction,confirmed,amount,sent,type,destination,time

The CSV input file can be produced with:
  chia wallet dump_transactions csv
using this patch:
  https://github.com/Chia-Network/chia-blockchain/tree/wallet_dump_transactions_2

Performs the following logic:
- Drops dust transactions
- Drops blocklisted transactions (e.g., NFT cancellation tx's which lack a
balancing tx)
- Aggregates spends in a block
- Aggregates recieves in a block
- If both spends & receives seen in one block, treats the recieve as change, and
the spend as the net spend (not the raw grosss spend, i.e. the value of the
spent coin).  This heuristic only works for the simple case of a single spend &
change-receipt transaction in one block.

BUGS:
- On my own data, this code is emitting as "receives" a couple incoming 1.7499..
  XCH transactions that would seem to actually be change for a 1.75 XCH coin
  during a few-mojo spend.  To avoid breaking things later on, I have a hook 
  that filters these.  However, we really should more robustly identify change
  coins (this may require better reporting from the Chia wallet).

OTHER KNOWN ISSUES:
- The change-coin heuristics are not reliable (as just mentioned)
- Multiple logical transactions that occur in one block will be conflated
- We don't do anything with transaction fees
"""
__copyright__ = "Copyright (C) 2023  Eric Altendorf"
__license__ = "GNU GPLv2"

import csv
import datetime
import decimal
import itertools
import logging
import re
from decimal import Decimal
from os import path
from typing import NamedTuple
from beancount.core.data import Posting, Transaction
from magicbeans.config import Config

import yaml
import pytz
from dateutil.parser import parse

import beangulp
import beancount.core
from beancount.core.number import ZERO, D
from beangulp.testing import main
from magicbeans import common
from magicbeans.transfers import Link, Network
from magicbeans.tripod import Tripod

# Surprisingly the Chia wallet dumps seem to be in local (PST) time.
# For now, we'll convert to UTC.  TODO: fix the Chia wallet dumper to
# report in UTC?
rendered_tz = 'US/Pacific'

class ChiaWalletImporter(beangulp.Importer):
    """An importer for Chia Wallet csv transaction files.
    
    In addition to the usual beancount configuration settings, this importer
    takes a Chia Wallet config which allows you to specify special processing
    of the Chia wallet transactions.  (TODO: integrate the Chia Wallet config
    with the broader magicbeans config.)
    
    The Chia Wallet config can be specified either as a path to a yaml file
    or as a dict directly.  The main fields to specify are:

    farming_reward_addrs: Known addresses to which farming rewards (coinbase/fee
    awards, or pool payouts) are sent.  Used as part of the heuristics to
    determine which incoming transfers 

    known_farming_reward_txs: If a farming reward is received in the same block
    as a spend tx, we are unable to distingiush it from a "change" coin going
    back to a farming address.  This is generally going to be rare, but if you
    find a farming reward misclassifeid by the change-coin heuristic, you can
    force it to be treated as a farming reward by adding its transaction ID
    here.
    
    blocklisted_txs: Transaction IDs to ignore, e.g. spurious outgoing
    transactions related to cancelation of an NFT offer.
    """

    # TODO: migrate away from supplying Network to supply Config only
    def __init__(self, account_root, account_mining_income,
                 account_gains, account_fees, network: Network,
                 config: Config = None,
                 chiawallet_config_path: str = None,
                 chiawallet_config_dict: dict = None):
        self.account_root = account_root
        self.account_mining_income = account_mining_income
        self.account_gains = account_gains
        self.account_fees = account_fees
        self.network = network
        if config:
            self.config = config

        if chiawallet_config_dict and chiawallet_config_path:
            raise ValueError("Cannot specify both chiawallet_config_path and chiawallet_config_dict")

        if chiawallet_config_path:
            with open(chiawallet_config_path, 'r') as f:
                self.chiawallet_config = yaml.load(f, Loader=yaml.FullLoader)
        else:
            self.chiawallet_config = {}

        if chiawallet_config_dict:
            self.chiawallet_config.update(chiawallet_config_dict)

    def name(self) -> str:
        return 'ChiaWallet'

    def identify(self, filepath):
        filename_re = r"^chiawallet.\d\d\d\d.\d\d.\d\d.csv$"
        if not re.match(filename_re, path.basename(filepath)):
            return False
            
        expected_header = 'Date,Received Quantity,Received Currency,Sent Quantity,' \
                          'Sent Currency,Fee Amount,Fee Currency,Tag'
        expected_header = 'token_name,transaction,confirmed,amount,sent,type,destination,time'
        if not common.file_begins_with(filepath, expected_header):
            return False

        return True

    def filename(self, filepath):
        return "coinbase.{}".format(path.basename(filepath))

    def account(self, filepath):
        return self.account_root

    def date(self, filepath):
        # Extract the statement date from the filename.
        return datetime.datetime.strptime(path.basename(filepath),
                                          "chiawallet.%Y.%m.%d.csv").date()

    # How we group rows ("transactions" from the wallet) and assume they're part
    # of the same "transaction".  We group together transactions at the same time
    # and of the same is coinbase reward (or not) status.  We can't group by pool
    # farming rewards because that takes additional analysis, except for the case
    # of specifically enumerated farming reward tx's.
    def key_record(self, row):
        # return row['time']
        return row['time'] + str(
                row['type'] in ['COINBASE_REWARD', 'FEE_REWARD']
                or row['transaction'] in self.chiawallet_config['known_farming_reward_txs'])

    def extract(self, filepath, existing):
        # Open the CSV file and create directives.
        entries = []
        index = 0

        # New direct from chia dump code
        with open(filepath) as infile:
            inreader = csv.DictReader(infile, delimiter=',', quotechar='"')
            for key, group in itertools.groupby(inreader, key=self.key_record):
                group_size = 0
                amount_out = decimal.Decimal(0)
                amount_in = decimal.Decimal(0)

                # Collect some facts about this group of transactions.
                has_coinbase_reward = False
                has_outgoing_tx = False
                has_incoming_tx = False
                has_incoming_to_farmer_reward_addr = False

                time = None

                # TODO: change all asserts to exceptions

                for row in group:
                    # n.b.: row['sent'] isn't what you think it is, and is irrelevant.
                    # It has to do with whether the tx has been sent to a node or something
                    # like that, not whether it is semantically a send transaction.

                    token_name = row['token_name']
                    if token_name in self.chiawallet_config['ignored_tokens']:
                        continue
                    if not token_name in self.chiawallet_config['allowed_tokens']:
                        raise Exception("Token: {token_name} not recognized")

                    if row['transaction'] in self.chiawallet_config['blocklisted_txs']:
                        continue

                    this_tx_time = datetime.datetime.fromisoformat(row['time'])
                    if not time in [None, this_tx_time]:
                        raise Exception("Transactions in a group must have the same time")
                    time = this_tx_time

                    amount = decimal.Decimal(row['amount'])
                    dst_addr = row['destination']
                    txtype = row['type']

                    # TODO: put this in the config
                    if amount < 0.000_000_000_010:
                        continue

                    group_size += 1

                    if (txtype in ['COINBASE_REWARD', 'FEE_REWARD']):
                        # Block rewards should always go to reward addresses.
                        assert dst_addr in self.chiawallet_config['farming_reward_addrs']
                        has_coinbase_reward = True
                        amount_in += amount

                    elif (txtype in ['OUTGOING_TX']):
                        # Outgoing tx should never go to farming reward addresses.
                        assert not dst_addr in self.chiawallet_config['farming_reward_addrs']
                        has_outgoing_tx = True
                        amount_out += amount

                    elif (txtype in ['INCOMING_TX']):
                        # This is the tricky case.  An incoming tx can be:
                        # - an actual receipt of a coin
                        # - a pool reward, marked as a farming reward
                        # - a change coin which needs to be discarded later
                        # We have to sort these out later.
                        has_incoming_tx = True
                        has_incoming_to_farmer_reward_addr = \
                            dst_addr in self.chiawallet_config['farming_reward_addrs']
                        amount_in += amount

                    else:
                        assert False

                # A group might be empty if it contained only (discarded) dust
                if group_size == 0:
                    continue

                # These are illegal but shouldn't happen because coinbase rewards shouldn't
                # ever get grouped with other transactions.
                assert not (has_coinbase_reward and has_outgoing_tx)
                assert not (has_coinbase_reward and has_incoming_tx)

                # As of 2023.03.28, the Chia wallet still reports spends with change in a
                # weird way.  The actual net spend amount is shown as a spend (amount_out),
                # and the received change coin is shown as a received coin even though the
                # gross spend coin doesn't show up at all.  This means essentially that we
                # need to ignore the change coin because it should be subtracted from the
                # spend coin that we don't see at all, while the send transaction we do see
                # is already the net amount.
                # 
                # We can't really tell which coins are change coins, but if we assume that
                # one block has at most one logical transaction (spend bundle) then any
                # block with both an amount_in and amount_out must represent a spend with
                # change.  Thus, we look for this case, and if we see it, we use the
                # amount_out and ignore the amount_in.
                #
                # As a further complication, at this point we finally decide for certain
                # ambiguous cases whether to treat an incoming tx as a farming reward.
                # Specifically, an INCOMING_TX to a farming reward address could either
                # be a pool payout, or a change coin from a spend.

                is_farming_reward = False
                if (amount_out > 0 and amount_in > 0):
                    assert not has_coinbase_reward
                    net_amount = -amount_out

                elif (amount_out > 0):
                    assert not has_coinbase_reward
                    assert not has_incoming_tx
                    net_amount = -amount_out

                elif (amount_in > 0):
                    assert not has_outgoing_tx
                    net_amount = amount_in
                    is_farming_reward = has_coinbase_reward or has_incoming_to_farmer_reward_addr 

                else:
                    assert False

                rcvd_quantity = net_amount if net_amount > 0 else ''
                rcvd_currency = token_name if net_amount > 0 else ''
                sent_quantity = -net_amount if net_amount < 0 else ''
                sent_currency = token_name if net_amount < 0 else ''

                meta = beancount.core.data.new_metadata(filepath, index)

                local_dt = pytz.timezone(rendered_tz).localize(time)
                utc_dt = local_dt.astimezone(pytz.timezone('UTC'))  # TODO: pytz.utc?
                tripod = Tripod(rcvd_quantity, rcvd_currency,
                                sent_quantity, sent_currency,
                                '', '')
                tag = 'mined' if is_farming_reward else 'transfer'
                if tag == "mined":
                    assert tripod.is_transfer()

                desc = ""
                if tag == "mined":
                    desc = f"Mining reward of {tripod.amount()} {tripod.currency()}"
                elif tripod.is_transfer():
                    desc = f"{tripod.narrate()}"
                else:
                    desc = "Unexpected transaction??"

                links = beancount.core.data.EMPTY_SET

                if tripod.is_transfer():
                    account_int = beancount.core.account.join(
                        self.account_root, tripod.currency())

                    if tag == "mined":
                        account_ext = beancount.core.account.join(
                            self.account_mining_income, "USD")  # TODO
                    else:
                        if tripod.rcvd:
                            account_ext = self.network.source(account_int, tripod.currency())
                        else:
                            account_ext = self.network.target(account_int, tripod.currency())

                    units = beancount.core.amount.Amount(tripod.amount(), tripod.currency())
                    sign = Decimal(1 if tripod.rcvd else -1)

                    xch_price = self.config.get_price_fetcher().get_price("XCH", utc_dt)
                    if xch_price == None:
                        xch_price = Decimal("0")
                    mined_cost_basis = beancount.core.position.Cost(xch_price, "USD", None, None)

                    txn = Transaction(meta, utc_dt.date(), beancount.core.flags.FLAG_OKAY,
                                      None, desc, beancount.core.data.EMPTY_SET, links,
                        [
                            Posting(account_int,
                                    beancount.core.amount.mul(units, sign),
                                    mined_cost_basis if (tag == "mined") else common.usd_cost_spec(tripod.currency()),
                                    None, None, None),
                            Posting(account_ext,
                                    None if (tag == "mined") else beancount.core.amount.mul(units, -sign),
                                    None if (tag == "mined") else common.usd_cost_spec(tripod.currency()),
                                    None, None, None),
                        ],
                    )
                    common.attach_timestamp(txn, utc_dt)

                elif tripod.is_transaction():
                    assert False, "Unexpected transaction in wallet (expect transfers only)"

                else:
                    assert False, "not handled yet"

                entries.append(txn)

        return entries