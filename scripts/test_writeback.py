"""
Test writeback to a single page: set ClusterId=99 and LoopLabel='test'.
Verifies pages.update works with notion-client v3.
"""
import sys
sys.path.insert(0, ".")

from src.config import NOTION_DATABASE_ID
from src.notion.client import get_client

DB_ID = NOTION_DATABASE_ID
client = get_client()

# Get first page
result = client.data_sources.query(data_source_id=DB_ID, page_size=1)
pages = result.get("results", [])
if not pages:
    print("No pages found!")
    sys.exit(1)

page = pages[0]
page_id = page["id"]
title_prop = page.get("properties", {}).get("Name", {})
title = "".join(t.get("plain_text", "") for t in title_prop.get("title", []))
print(f"Testing writeback on page: [{title}] ({page_id})")

# Test pages.update with our new properties
try:
    result = client.pages.update(
        page_id=page_id,
        properties={
            "ClusterId": {"number": 99},
            "LoopLabel": {
                "rich_text": [{"type": "text", "text": {"content": "test-writeback"}}]
            },
        }
    )
    # Verify
    updated_cluster = result.get("properties", {}).get("ClusterId", {}).get("number")
    updated_label_rich = result.get("properties", {}).get("LoopLabel", {}).get("rich_text", [])
    updated_label = "".join(r.get("plain_text", "") for r in updated_label_rich)
    print(f"SUCCESS! ClusterId={updated_cluster}, LoopLabel='{updated_label}'")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

# Clean up: reset to empty
try:
    client.pages.update(
        page_id=page_id,
        properties={
            "ClusterId": {"number": None},
            "LoopLabel": {"rich_text": []},
        }
    )
    print("Cleaned up test values.")
except Exception as e:
    print(f"Cleanup warning: {e}")

print("\nWriteback test passed!")
