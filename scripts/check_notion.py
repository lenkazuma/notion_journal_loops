"""Quick script to list all accessible Notion databases."""
import sys
sys.path.insert(0, ".")

from src.notion.client import get_client

client = get_client()

result = client.search(filter={"property": "object", "value": "data_source"})
dbs = result.get("results", [])
print(f"找到 {len(dbs)} 个数据库:")
for db in dbs:
    title_list = db.get("title", [])
    title = "".join(t.get("plain_text", "") for t in title_list)
    db_id = db["id"]
    print(f"  ID: {db_id}")
    print(f"  Title: {title}")
    print()
