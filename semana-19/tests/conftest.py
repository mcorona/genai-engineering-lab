"""Shared pytest settings for week 19 tests."""


def pytest_configure(config):
    # "vivo" marks tests that need a local throwaway database (never the lab). CI deselects them with -m "not vivo".
    config.addinivalue_line("markers", "vivo: live test that needs a local throwaway database (S19_DSN_LOCAL)")
