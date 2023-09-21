import datetime
from beancount.core.number import D
from magicbeans import gen_example
import pytest

def test_sd_round():
    assert gen_example.sd_round(D('1234'), 2) == D('1200')
    assert gen_example.sd_round(D('0.01537'), 2) == D('0.015')

    assert gen_example.sd_round(D('0.01599'), 2) == D('0.015')

    assert gen_example.sd_round(D('1234'), 3) == D('1230')
    assert gen_example.sd_round(D('0.01537'), 3) == D('0.0153')

    assert gen_example.sd_round(D('1234'), 4) == D('1234')
    assert gen_example.sd_round(D('1234'), 6) == D('1234')