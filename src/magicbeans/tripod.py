"""Represents the common class of transaction with a received and/or sent leg,
and an optional fees leg.  Enforces internal consistency and offers higher-level
views of the data, e.g. as a transaction or an account transfer.  Does not
classify between "buy" and "sell" transactions, since those labels only make
sense in the context of a leg in the operating currency (e.g., BTC for USD), and
conversely, in the context of taxation, events that don't seem to be sales need
to be treated as sales (e.g. payment of transaction fees in non-USD assets)."""

# TODO: add tests

from decimal import Decimal
from beancount.core.number import D

def check_booleq_and_return(val1, val2):
    if bool(val1) != bool(val2):
        raise Exception("Only one value (should be both or neither): " \
                        f"val1={val1} val2={val2}")
    return bool(val1)

class Tripod():
    """A tripod represents a transaction with up to three legs (received, sent,
    and fees), from the perspective of one account.  Therefore, each amount is
    represented as a positive value.  At least one of {received, sent} is
    required, and if both are present, then their currencies must differ."""
    def __init__(self,
                 rcvd_amt: str, rcvd_cur: str,
                 sent_amt: str, sent_cur: str,
                 fees_amt: str, fees_cur: str):
        self.rcvd: bool = check_booleq_and_return(rcvd_cur, rcvd_amt)
        self.sent: bool = check_booleq_and_return(sent_cur, sent_amt)
        self.fees: bool = check_booleq_and_return(fees_cur, fees_amt)

        self.rcvd_amt: Decimal = D(rcvd_amt)
        self.rcvd_cur: str = rcvd_cur
        self.sent_amt: Decimal = D(sent_amt)
        self.sent_cur: str = sent_cur
        self.fees_amt: Decimal = D(fees_amt)
        self.fees_cur: str = fees_cur

        if self.rcvd_amt < 0:
            raise Exception("Negative received amount")
        if self.sent_amt < 0:
            raise Exception("Negative sent amount")
        if self.fees_amt < 0:
            raise Exception("Negative fees amount")

        # This is here because we currently have no fee-only transactions,
        # but it could be removed, e.g., for account maintenance fees.
        if not self.rcvd and not self.sent:
            raise Exception("Must have recieved and/or sent")
        
        if self.is_transaction() and self.rcvd_cur == self.sent_cur:
            raise Exception("Appears to be a transaction (assets both sent and "
                            "received) but sent and received currencies are the "
                            f"same: {self.rcvd_cur}")

    def is_transaction(self) -> bool:
        return self.rcvd and self.sent

    def is_transfer(self) -> bool:
        return not self.is_transaction()

    def is_send(self) -> bool:
        return self.is_transfer() and self.sent

    def is_receive(self) -> bool:
        return self.is_transfer() and self.rcvd

    def xfer_amt(self) -> str:
        if not self.is_transfer():
            raise Exception("Can't get transfer currency on non transfer")
        if self.is_send():
            return self.sent_amt
        else:
            return self.rcvd_amt

    def xfer_cur(self) -> str:
        if not self.is_transfer():
            raise Exception("Can't get transfer currency on non transfer")
        if self.is_send():
            return self.sent_cur
        else:
            return self.rcvd_cur

    # TODO: maybe need a flag to say whether to subtract out fee amounts or not
    def imputed_price(self, target_currency) -> Decimal:
        if not self.is_transaction():
            raise Exception("Price imputation only defined on transactions")
        if self.rcvd_cur == target_currency:
            return Decimal(self.sent_amt / self.rcvd_amt)
        elif self.sent_cur == target_currency:
            return Decimal(self.rcvd_amt / self.sent_amt)
        else:
            raise Exception(
                f"Can't impute price in target currency {target_currency}; " \
                f"doesn't match sent currency {self.sent_cur}" \
                f"or received currency {self.rcvd_cur}")

    def currency(self) -> str:
        if not self.is_transfer():
            raise Exception("Single currency only defined on transfers")
        return self.rcvd_cur or self.sent_cur
    
    def amount(self) -> Decimal:
        if not self.is_transfer():
            raise Exception("Single amount only defined on transfers")
        return self.rcvd_amt or self.sent_amt

    def tx_class(self) -> str:
        if self.is_transaction():
            return "Transaction"
        elif self.is_transfer():
            if self.sent_amt:
                return "Send"
            else:
                return "Receive"