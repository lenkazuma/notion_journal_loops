"""Check current database schema and test property update."""
import sys, json
sys.path.insert(0, ".")

from src.config import NOTION_DATABASE_ID
from src.notion.client import get_client

DB_ID = NOTION_DATABASE_ID
client = get_client()

print("=== Current Database Properties ===")
db = client.data_sources.retrieve(data_source_id=DB_ID)
props = db.get("properties", {})
for name, prop in sorted(props.items()):
    ptype = prop.get("type", "?")
    print(f"  [{ptype:20s}] {name}")

print(f"\nTotal: {len(props)} properties")

# Check if our writeback properties already exist
needed = ["ClusterId", "LoopLabel", "IsDuplicate", "CanonicalPage", "CanonicalChunk"]
print("\n=== Writeback Properties Status ===")
for n in needed:
    exists = n in props
    print(f"  {'✓' if exists else '✗'} {n}")
