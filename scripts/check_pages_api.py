"""Check what methods are available on pages endpoint in notion-client v3."""
import sys
sys.path.insert(0, ".")

from src.notion.client import get_client

c = get_client()
print("pages methods:", [m for m in dir(c.pages) if not m.startswith("_")])
print("data_sources methods:", [m for m in dir(c.data_sources) if not m.startswith("_")])
