"""
Create writeback properties in the Notion database if they don't exist.
Run this once before using writeback_notion.py.

Properties created:
  - ClusterId     (number)
  - LoopLabel     (rich_text)
  - IsDuplicate   (checkbox)
  - CanonicalPage (url)
  - CanonicalChunk (rich_text)
"""
import sys
sys.path.insert(0, ".")

from notion_client import Client

TOKEN = "NOTION_TOKEN_PLACEHOLDER"
DB_ID = "YOUR_NOTION_DATABASE_ID"
client = Client(auth=TOKEN)

NEEDED_PROPS = {
    "ClusterId":      {"number": {"format": "number"}},
    "LoopLabel":      {"rich_text": {}},
    "IsDuplicate":    {"checkbox": {}},
    "CanonicalPage":  {"url": {}},
    "CanonicalChunk": {"rich_text": {}},
}

print("=== Checking existing properties ===")
db = client.data_sources.retrieve(data_source_id=DB_ID)
existing = set(db.get("properties", {}).keys())
print(f"Existing: {sorted(existing)}")

to_create = {k: v for k, v in NEEDED_PROPS.items() if k not in existing}
if not to_create:
    print("\nAll writeback properties already exist!")
    sys.exit(0)

print(f"\nCreating {len(to_create)} properties: {list(to_create.keys())}")

# data_sources.update to add properties (notion-client v3)
result = client.data_sources.update(
    data_source_id=DB_ID,
    properties=to_create,
)
created = set(result.get("properties", {}).keys())
print("\nProperties after update:")
for name in sorted(created):
    mark = "✓ NEW" if name in to_create else "  "
    print(f"  {mark} {name}")

print("\nDone! Writeback properties are ready.")
