"""Inspect create method signatures."""
import inspect
from notion_client import Client
c = Client(auth="NOTION_TOKEN_PLACEHOLDER")

print("=== pages.create signature ===")
print(inspect.getsource(c.pages.create))
print()
print("=== data_sources.create signature ===")
print(inspect.getsource(c.data_sources.create))
