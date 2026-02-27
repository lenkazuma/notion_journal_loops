"""Check current database schema and test property update."""
import sys, json
sys.path.insert(0, ".")

from notion_client import Client

TOKEN = "NOTION_TOKEN_PLACEHOLDER"
DB_ID = "YOUR_NOTION_DATABASE_ID"
client = Client(auth=TOKEN)

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
