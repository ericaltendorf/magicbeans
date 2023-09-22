import datetime
from beancount.core.number import D
from magicbeans.gen_example import sd_round, rcvd_cur_choices
import pytest

def test_sd_round():
    assert sd_round(D('1234'), 2) == D('1200')
    assert sd_round(D('0.01537'), 2) == D('0.015')

    assert sd_round(D('0.01599'), 2) == D('0.015')

    assert sd_round(D('1234'), 3) == D('1230')
    assert sd_round(D('0.01537'), 3) == D('0.0153')

    assert sd_round(D('1234'), 4) == D('1234')
    assert sd_round(D('1234'), 6) == D('1234')

def test_rcvd_cur_choices__pre_post_xch():
    pre_xch = datetime.date(2021, 4, 30)
    post_xch = datetime.date(2021, 7, 30)
    assert set(rcvd_cur_choices(pre_xch, "USD")) == set(["BTC", "ETH", "USDT"])
    assert set(rcvd_cur_choices(post_xch, "USD")) == set(["BTC", "ETH", "USDT", "XCH"])

def test_rcvd_cur_choices__usdt_disposal():
    pre_xch = datetime.date(2021, 4, 30)
    assert set(rcvd_cur_choices(pre_xch, "USDT")) == set(["BTC", "ETH", "USD"])

def test_rcvd_cur_choices__crypto_disposal():
    pre_xch = datetime.date(2021, 4, 30)
    assert set(rcvd_cur_choices(pre_xch, "BTC")) == set(["USD", "USDT"])
