"""Inspect create method signatures."""
import inspect
import sys
sys.path.insert(0, ".")

from src.notion.client import get_client

c = get_client()

print("=== pages.create signature ===")
print(inspect.getsource(c.pages.create))
print()
print("=== data_sources.create signature ===")
print(inspect.getsource(c.data_sources.create))
