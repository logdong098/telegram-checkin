import pytest
def pytest_collection_modifyitems(config, items):
    for item in items:
        if "asyncio" in item.keywords: continue
