# This isn't working right now.  TODO: fix.  See conftest.py also.

# from beangulp import regression_pytest
# from magicbeans._tests import mocks

# from magicbeans.importers.chiawallet import ChiaWalletImporter
# from magicbeans.importers.coinbase import CoinbaseImporter
# from magicbeans.importers.coinbasepro import CoinbaseProImporter
# from magicbeans.importers.gateio import GateIOImporter

# # Coinbase
# @regression_pytest.with_importer(CoinbaseImporter.test_instance())
# @regression_pytest.with_testdir("_tests/importer_files/coinbase/")
# class TestCoinbaseImporter(regression_pytest.ImporterTestBase):
#     pass

# # CoinbasePro
# @regression_pytest.with_importer(mocks.coinbasepro_importer_for_testing())
# @regression_pytest.with_testdir("_tests/importer_files/coinbasepro/")
# class TestCoinbaseProImporter(regression_pytest.ImporterTestBase):
#     pass

# # GateIO
# @regression_pytest.with_importer(mocks.gateio_importer_for_testing())
# @regression_pytest.with_testdir("_tests/importer_files/gateio/")
# class TestGateIOImporter(regression_pytest.ImporterTestBase):
#     pass

# # ChiaWallet
# @regression_pytest.with_importer(mocks.chia_wallet_importer_for_testing())
# @regression_pytest.with_testdir("_tests/importer_files/chiawallet/")
# class TestChiaWalletImporter(regression_pytest.ImporterTestBase):
#     pass