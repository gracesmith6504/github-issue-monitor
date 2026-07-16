import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: hits real APIs (LLM, GitHub)")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("-m", default=None):
        skip = pytest.mark.skip(reason="slow test — run with: pytest -m slow")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip)
