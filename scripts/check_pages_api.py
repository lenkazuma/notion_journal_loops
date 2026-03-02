"""Check what methods are available on pages endpoint in notion-client v3."""
from notion_client import Client
c = Client(auth="NOTION_TOKEN_PLACEHOLDER")
print("pages methods:", [m for m in dir(c.pages) if not m.startswith("_")])
print("data_sources methods:", [m for m in dir(c.data_sources) if not m.startswith("_")])
