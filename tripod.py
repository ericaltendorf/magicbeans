"""Represents the common class of transaction with a received and/or 
   sent leg, and an optional fees leg.  Enforces internal consistency
   and offers higher-level views of the data, e.g. as a buy/sell
   transaction or an account transfer."""

# TODO: add tests

from decimal import Decimal
from beancount.core.number import D

def check_booleq_and_return(val1, val2):
    if bool(val1) != bool(val2):
        raise Exception("Only one value (should be both or neither): " \
                        f"val1={val1} val2={val2}")
    return bool(val1)

class Tripod():
    """A tripod has up to three legs: received, sent, and fees.  At least
       one of {received, sent} is required, and if both are present, then
       their currencies must differ."""
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

        if not self.rcvd and not self.sent:
            raise Exception("Must have recieved and/or sent")
        
        if self.is_transaction() and self.rcvd_cur == self.sent_cur:
            raise Exception("Appears to be a transaction (assets both sent and "
                            "received) but sent and received currencies are the "
                            f"same: {self.rcvd_cur}")

    def is_transaction(self):
        return self.rcvd and self.sent

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

    def is_transfer(self):
        return not self.is_transaction()

    def currency(self):
        if not self.is_transfer():
            raise Exception("Single currency only defined on transfers")
        return self.rcvd_cur or self.sent_cur
    
    def amount(self):
        if not self.is_transfer():
            raise Exception("Single amount only defined on transfers")
        return self.rcvd_amt or self.sent_amt

    def description(self):
        if self.is_transaction():
            return "Transaction"
        elif self.is_transfer():
            return "Transfer"