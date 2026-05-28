"""Test Notion database query and block fetch."""
import sys
sys.path.insert(0, ".")

from src.config import NOTION_DATABASE_ID
from src.notion.client import get_client

DB_ID = NOTION_DATABASE_ID
client = get_client()

# Query first 3 pages
print("=== Querying database (first 3 pages) ===")
result = client.data_sources.query(data_source_id=DB_ID, page_size=3)
pages = result.get("results", [])
print(f"Got {len(pages)} pages")

for page in pages:
    pid = page["id"]
    props = page.get("properties", {})
    # Find title
    title = ""
    for k, v in props.items():
        if v.get("type") == "title":
            title = "".join(t.get("plain_text","") for t in v.get("title",[]))
            break
    # Find date
    date = page.get("created_time","")[:10]
    for k, v in props.items():
        if v.get("type") == "date" and v.get("date"):
            date = v["date"].get("start","")[:10]
            break
    print(f"\n  Page: {title} | Date: {date} | ID: {pid}")

    # Fetch first page's blocks
    if page == pages[0]:
        print("\n=== Fetching blocks for first page ===")
        blocks_result = client.blocks.children.list(block_id=pid, page_size=5)
        blocks = blocks_result.get("results", [])
        print(f"Got {len(blocks)} blocks (first 5)")
        for b in blocks[:3]:
            btype = b.get("type","")
            content = b.get(btype, {})
            rich = content.get("rich_text", []) if isinstance(content, dict) else []
            text = "".join(r.get("plain_text","") for r in rich)
            print(f"  [{btype}] {text[:80]}")
