"""Quick script to list all accessible Notion databases."""
import sys
sys.path.insert(0, ".")

from notion_client import Client

TOKEN = "NOTION_TOKEN_PLACEHOLDER"
client = Client(auth=TOKEN)

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
