from decimal import Decimal
from beancount.core.position import Position
from beancount.parser import booking_method as beancount_methods

def booking_method_MAGICBEANS(entry, posting, matches):
    """
    Magicbeans custom booking method.

    Magicbeans depends heaviliy on the automatic booking functionality, and 
    has somewhat elaborate requirements for it.  This is a booking method
    which:

    - Allows for different booking methods at different times, e.g., in case
    one changes booking methods from year to year

    - Supports booking in the context of transfers from one account to another,
    which requires special handling especially in the context of crypto,
    since transfers from an exchange to cold storage typically should follow
    the inverse logic compared to bookings for a sale.
    """

    # If there's no price, it's probably a transfer rather than a sale.  The
    # posting we get is the reduction (donating account).
    is_sale = posting.price is not None

    # If the posting is on a wallet account, it's probably a transfer to a
    # trading account in preparation for sale, so we would want to pick the
    # lot with minimal tax liability.
    #
    # If the posting is on a trading account, then it's probably a transfer to a
    # wallet and we want the inverse -- to stash away the lots least desirable
    # to sell.
    sale_prep = "Wallet" in posting.account  # Total hack

    # TODO: reorganize by year
    if is_sale:
        return beancount_methods.booking_method_HIFO(entry, posting, matches)
    elif entry.date.year < 2022:
        return beancount_methods.booking_method_HIFO(entry, posting, matches)
    elif sale_prep:
        return beancount_methods.booking_method_HIFO(entry, posting, matches)
    else:
        return booking_method_LowIFO(entry, posting, matches)

def booking_method_LowIFO(entry, posting, matches):
    """Lowest-In First Out booking method implementation.  Used internally for
    transfers."""

    return beancount_methods._booking_method_xifo(
        entry,
        posting,
        matches,
        lambda m: m.cost and getattr(m.cost, "number"),
        # "number",
        reverse_order=False,
    )

# TODO: Integrate this into the MAGICBEANS method somehow
def booking_method_LTFO(entry, posting, matches):
    """LTFO (least tax first out, ish) booking method implementation.
    
    This will attempt to minimize the tax liability of the sale by considering
    both gain/loss and the long/short term holding period (including preferring
    losses over gains, i.e. tax loss harvesting).  It will also use some
    heuristics on transfers.  (TODO: What heuristics?)
    """
    # US tax rules
    lt_rate = Decimal("0.2")
    st_rate = Decimal("0.4")
    def lt_thresh(match: Position):
        return match.cost.date.replace(year=match.cost.date.year + 1)

    # If we have a price on the posting, then we can compute the tax liability
    # for each match and select the one with the lowest tax liability.

    if posting.price:
        def us_tax_liability(match: Position):
            """Compute the US tax liability (per unit) of a given match."""
            gain_per_unit = posting.price.number - match.cost.number
            lt_threshold = lt_thresh(match)
            tax_rate = lt_rate if entry.date >= lt_threshold else st_rate
            return gain_per_unit * tax_rate

        # TODO: For this to work, _booking_method_xifo needs to be updated
        # to take a lamba rather than just a field name.
        return beancount_methods._booking_method_xifo(
            entry, posting, matches, us_tax_liability, reverse_order=False
        )

    # If there's no price, it's probably a transfer rather than a sale.  The
    # posting we get is the reduction (donating account).
    #
    # If the posting is on a wallet account, it's probably a transfer to a
    # trading account in preparation for sale, so we would want to pick the
    # lot with minimal tax liability.
    #
    # If the posting is on a trading account, then it's probably a transfer to a
    # wallet and we want the inverse -- to stash away the lots least desirable
    # to sell.
    #
    # Now, how do we estimate the tax liability without a price?  Well, if
    # all matches have the same short/long term status, we can just use the
    # cost basis (highest, or lowest, depending on the account).

    sale_prep = "Wallet" in posting.account  # Total hack

    def is_lt(match: Position):
        return entry.date > lt_thresh(match)

    if all(is_lt(m) for m in matches) or all(not is_lt(m) for m in matches):
        if sale_prep:
            return beancount_methods.booking_method_HIFO(entry, posting, matches)
        else:
            return booking_method_LowIFO(entry, posting, matches)

    # OK, this is the hard case, it's a transfer, we don't know the price,
    # and we have a mix of long and short term lots.  For now, do the same
    # as when there's no short/long mix.  TODO: be smarter?
    if sale_prep:
        return beancount_methods.booking_method_HIFO(entry, posting, matches)
    else:
        return booking_method_LowIFO(entry, posting, matches)

# TODO: Figure out how to run this test in magicbeans (it relies
# on some beancount test infrastructure)

# @book_test(Booking.LTFO)
# def test_reduce__multiple_reductions_ltfo(self, _, __):
#     """
#     2016-01-01 * #ante
#       ;; Sell LT @ 140 USD = 60 USD * 20% = 12 USD tax ea
#       Assets:Account           50 HOOL {80.00 USD, 2016-01-01}
#       ;; Sell LT @ 140 USD = 20 USD * 20% = 4 USD tax ea
#       Assets:Account           50 HOOL {120.00 USD, 2016-01-01}
#       ;; Sell ST @ 140 USD = 25 USD * 40% = 10 USD tax ea
#       Assets:Account           50 HOOL {115.00 USD, 2017-01-01}
#     2017-03-01 * #apply
#       Assets:Account          -40 HOOL {} @ 140.00 USD
#       Assets:Account          -40 HOOL {} @ 140.00 USD
#     2017-03-01 * #booked
#       Assets:Account          -40 HOOL {120.00 USD, 2016-01-01} @ 140.00 USD
#       Assets:Account          -10 HOOL {120.00 USD, 2016-01-01} @ 140.00 USD
#       Assets:Account          -30 HOOL {115.00 USD, 2017-01-01} @ 140.00 USD
#     2016-01-01 * #ex
#       Assets:Account           50 HOOL {80.00 USD, 2016-01-01}
#       Assets:Account           20 HOOL {115.00 USD, 2017-01-01}
#     """
