"""
Create a summary Notion page with two sections:
  A) 文字重复：chunk text is nearly identical (after filtering image/URL noise)
  B) 主题重复：same page appears in multiple clusters / high semantic similarity
     but content is different text (same emotional theme recurring over time)

Run: python scripts/create_dup_summary_page.py [--dry-run]
"""
from __future__ import annotations
import sys, json, re, argparse, time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from src.config import DUP_SIM_THRESHOLD, NOTION_DATABASE_ID, OPENAI_EMBED_MODEL, RAW_DIR
from src.notion.client import get_client
from src.utils.logger import get_logger

logger = get_logger("create_dup_summary")

DB_ID = NOTION_DATABASE_ID
client = get_client()

# ── helpers ──────────────────────────────────────────────────────────────────

def notion_url(page_id: str) -> str:
    return f"https://www.notion.so/{page_id.replace('-', '')}"

def is_url_noise(text: str) -> bool:
    """
    Return True if the text is mostly image/S3/CDN URL content.
    Handles cases where URLs contain embedded newlines (Notion block chunking).
    """
    t = text or ""
    # Quick check: if text contains S3/CDN keywords, it's likely URL noise
    noise_keywords = ["amazonaws.com", "X-Amz-", "prod-files-secure", "UNSIGNED-PAYLOAD"]
    if any(kw in t for kw in noise_keywords):
        return True
    # Strip [image: ...] / [video: ...] / [file: ...] blocks (multiline)
    t = re.sub(r'\[(?:image|video|file|bookmark|pdf)\s*:.*?\]', '', t,
               flags=re.IGNORECASE | re.DOTALL)
    # Strip leftover bracket shells
    t = re.sub(r'\[(?:image|video|file|bookmark|pdf)\s*:?\s*\]', '', t, flags=re.IGNORECASE)
    # Strip long URLs
    t = re.sub(r'https?://\S{20,}', '', t)
    # Strip URL query params
    t = re.sub(r'[A-Za-z0-9%_-]+=(?:[A-Za-z0-9%_/+.=-]{15,})', '', t)
    return len(t.strip()) < 80

def load_page_text(page_id: str) -> str:
    p = Path(f"data/raw/pages/{page_id}.json")
    return json.loads(p.read_text(encoding="utf-8")).get("raw_text", "") if p.exists() else ""

# ── load data ─────────────────────────────────────────────────────────────────

all_dups = json.loads(open("data/clusters/duplicates.json", encoding="utf-8").read())
dups_24  = [d for d in all_dups if d.get("dup_date", "")[:4] >= "2024"]

# ── Section A: true text duplicates (chunk text is not URL noise) ─────────────

text_dups = [d for d in dups_24
             if not is_url_noise(d.get("dup_text",""))
             and not is_url_noise(d.get("canonical_text",""))]

# Group by (dup_page, canonical_page) pair
text_pairs: dict[tuple, dict] = {}
for d in text_dups:
    key = (d["dup_page_id"], d["canonical_page_id"])
    if key not in text_pairs:
        text_pairs[key] = {
            "dup_title":       d["dup_page_title"],
            "dup_date":        d["dup_date"],
            "dup_pid":         d["dup_page_id"],
            "canonical_title": d["canonical_page_title"],
            "canonical_date":  d["canonical_date"],
            "canonical_pid":   d["canonical_page_id"],
            "chunks": [],
        }
    text_pairs[key]["chunks"].append(d)

text_rows = sorted(text_pairs.values(), key=lambda x: x["dup_date"])

# ── Section B: image-noise pages (pages that contain images causing false hits) ─

image_noise_pages: dict[str, dict] = {}
url_dups = [d for d in dups_24
            if is_url_noise(d.get("dup_text","")) or is_url_noise(d.get("canonical_text",""))]

# Collect unique dup pages that have image-URL chunks
for d in url_dups:
    if is_url_noise(d.get("dup_text","")):
        pid = d["dup_page_id"]
        if pid not in image_noise_pages:
            image_noise_pages[pid] = {
                "title": d["dup_page_title"],
                "date":  d["dup_date"],
                "pid":   pid,
                "n_chunks": 0,
            }
        image_noise_pages[pid]["n_chunks"] += 1

image_rows = sorted(image_noise_pages.values(), key=lambda x: x["date"])

logger.info(f"Text duplicates (2024+): {len(text_dups)} chunks across {len(text_rows)} page-pairs")
logger.info(f"Image-noise pages (2024+): {len(image_rows)} pages")

# ── Notion block builders ─────────────────────────────────────────────────────

def rich(text: str, bold=False, color=None) -> dict:
    r: dict = {"type": "text", "text": {"content": text}}
    ann: dict = {}
    if bold:  ann["bold"] = True
    if color: ann["color"] = color
    if ann:   r["annotations"] = ann
    return r

def link_rich(text: str, url: str, bold=False, color=None) -> dict:
    r: dict = {"type": "text", "text": {"content": text, "link": {"url": url}}}
    ann: dict = {}
    if bold:  ann["bold"] = True
    if color: ann["color"] = color
    if ann:   r["annotations"] = ann
    return r

def para(*parts) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": list(parts)}}

def h2(text: str) -> dict:
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [rich(text, bold=True)]}}

def h3(text: str) -> dict:
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [rich(text)]}}

def divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}

def callout(text: str, emoji: str = "ℹ️", color: str = "gray_background") -> dict:
    return {"object": "block", "type": "callout",
            "callout": {"rich_text": [rich(text)],
                        "icon": {"type": "emoji", "emoji": emoji},
                        "color": color}}

def bullet(*parts) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": list(parts)}}

def spacer() -> dict:
    return para(rich(""))

# ── assemble blocks ───────────────────────────────────────────────────────────

now = datetime.now().strftime("%Y-%m-%d %H:%M")
blocks: list[dict] = []

# ── header callout ────────────────────────────────────────────────────────────
blocks.append(callout(
    f"自动生成于 {now}。"
    f"仅分析 2024 年及以后的日记。"
    f"使用 {OPENAI_EMBED_MODEL}，相似度阈值 ≥ {DUP_SIM_THRESHOLD}。",
    "🤖"
))
blocks.append(divider())

# ── overview ──────────────────────────────────────────────────────────────────
total_pages = len(list((RAW_DIR / "pages").glob("*.json")))
blocks.append(h2("📊 概览"))
blocks.append(para(
    rich(f"扫描日记总数：{total_pages} 篇　　分析范围：2024-01-01 至今\n"
         f"发现文字重复：{len(text_dups)} 个片段，涉及 {len(text_rows)} 对页面\n"
         f"含图片/附件的页面（图片URL导致误报，已单独列出）：{len(image_rows)} 篇")
))
blocks.append(divider())

# ── Section A: Text Duplicates ────────────────────────────────────────────────
blocks.append(h2("🔴 A. 文字重复（内容几乎相同）"))

if not text_rows:
    blocks.append(callout("✅ 未检测到真实文字重复（2024年后）。", "✅", "green_background"))
else:
    blocks.append(para(
        rich("以下页面的部分段落与更早的日记内容高度相似（相似度 ≥ 0.92）。"
             "建议打开两篇对比，确认是否为复制粘贴或重复记录。")
    ))
    blocks.append(spacer())

    for i, row in enumerate(text_rows, 1):
        dup_url = notion_url(row["dup_pid"])
        can_url = notion_url(row["canonical_pid"])
        max_sim = max(c["similarity"] for c in row["chunks"])
        n       = len(row["chunks"])

        blocks.append(h3(f"{i}. {row['dup_title']}  →  {row['canonical_title']}"))
        blocks.append(para(
            rich("重复页面：", bold=True),
            link_rich(row["dup_title"], dup_url),
            rich(f"  （{row['dup_date']}）　　"),
            rich("原始页面：", bold=True),
            link_rich(row["canonical_title"], can_url),
            rich(f"  （{row['canonical_date']}）"),
        ))
        blocks.append(para(
            rich(f"相似度：{max_sim:.3f}　　重复片段数：{n}　　"),
            rich("建议：检查是否可合并或删除重复版本", color="red"),
        ))

        for c in row["chunks"][:3]:
            dup_p = c.get("dup_text","")[:100].replace("\n"," ")
            can_p = c.get("canonical_text","")[:100].replace("\n"," ")
            blocks.append(bullet(
                rich(f"重复段落（sim={c['similarity']:.3f}）：", bold=True),
            ))
            blocks.append(bullet(
                rich(f"  此页：「{dup_p}…」", color="red"),
            ))
            blocks.append(bullet(
                rich(f"  原始：「{can_p}…」", color="gray"),
            ))
        blocks.append(spacer())

blocks.append(divider())

# ── Section B: Image-noise pages ─────────────────────────────────────────────
blocks.append(h2("🟡 B. 含图片/附件的页面（误报说明）"))
blocks.append(para(
    rich("以下页面因包含 Notion 图片或附件，其图片的临时签名 URL（S3 链接）"
         "在 embedding 空间中极为相似，导致被误判为「重复」。"
         "这些页面的文字内容本身并无重复，无需处理。")
))
blocks.append(spacer())

if not image_rows:
    blocks.append(para(rich("无。")))
else:
    for row in image_rows:
        url = notion_url(row["pid"])
        blocks.append(bullet(
            link_rich(row["title"], url, bold=True),
            rich(f"  （{row['date']}）　含图片 chunk 数：{row['n_chunks']}"),
        ))

blocks.append(divider())

# ── Section C: How to handle ─────────────────────────────────────────────────
blocks.append(h2("💡 处理建议"))
blocks.append(para(rich(
    "A 类（文字重复）：\n"
    "  • 相似度 ≥ 0.98：几乎完全相同，很可能是复制粘贴或重复导入，建议删除较晚的版本。\n"
    "  • 相似度 0.92–0.97：主题/情绪高度相似，属于同一情绪循环在不同时期的记录，可保留两者，但值得关注。\n\n"
    "B 类（图片页面）：无需处理，这是技术误报。\n\n"
    "如需批量在 Notion 页面中标注删除线，运行：\n"
    "  python -m src.writeback.writeback_notion --mode dryrun"
)))

# ── create the page ───────────────────────────────────────────────────────────

def get_data_source_id() -> str:
    """
    In notion-client v3 (API 2025-09-03+), pages.create with a database parent
    requires data_source_id instead of database_id.
    Retrieve it from the database object via GET /v1/databases/:id.
    """
    try:
        # Use databases.retrieve (not data_sources.retrieve) to get the data_sources array
        db = client.databases.retrieve(database_id=DB_ID)
        data_sources = db.get("data_sources", [])
        if data_sources:
            dsid = data_sources[0].get("id", DB_ID)
            logger.info(f"Retrieved data_source_id: {dsid}")
            return dsid
    except Exception as e:
        logger.warning(f"Could not retrieve data_source_id: {e}, falling back to DB_ID")
    return DB_ID


def create_page(dry_run: bool) -> None:
    title = f"[自动] 重复内容分析报告 {datetime.now().strftime('%Y-%m-%d')}"
    logger.info(f"{'[DRY-RUN] Would create' if dry_run else 'Creating'} page: {title}")
    logger.info(f"  Total blocks: {len(blocks)}")

    if dry_run:
        for b in blocks:
            btype = b.get("type","")
            content = b.get(btype, {})
            rt = content.get("rich_text", []) if isinstance(content, dict) else []
            text = "".join(r.get("text",{}).get("content","") for r in rt)
            print(f"  [{btype:15s}] {text[:80]}")
        return

    # Get the data_source_id for page creation (v3 API requires data_source_id parent)
    data_source_id = get_data_source_id()

    # Create page with first 100 blocks
    # v3 API: parent must use {"type": "data_source_id", "data_source_id": "..."}
    page = client.pages.create(
        parent={"type": "data_source_id", "data_source_id": data_source_id},
        properties={
            "Name": {"title": [{"type": "text", "text": {"content": title}}]},
            "Tags": {"multi_select": [{"name": "自动生成"}, {"name": "重复分析"}]},
        },
        children=blocks[:100],
    )
    page_id = page["id"]
    logger.info(f"Created: {notion_url(page_id)}")

    # Append remaining blocks in batches of 100
    for start in range(100, len(blocks), 100):
        time.sleep(0.5)
        client.blocks.children.append(
            block_id=page_id,
            children=blocks[start:start+100],
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    create_page(dry_run=args.dry_run)
