"""
Apply strikethrough annotation ONLY to Class-A (true text) duplicates.
Filters out image/URL noise chunks before writing to Notion.

Actions per duplicate chunk:
  1. Append a "(Duplicate of: <link>)" notice paragraph to the dup page
  2. Append the duplicate text with strikethrough + gray color
  3. Update page properties: IsDuplicate=True, CanonicalPage=<url>

Run:
  python scripts/apply_strikethrough_class_a.py --dry-run   # preview
  python scripts/apply_strikethrough_class_a.py             # write to Notion
"""
from __future__ import annotations
import sys, json, re, argparse, time
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from src.notion.client import get_client
from src.utils.logger import get_logger

logger = get_logger("strikethrough_class_a")

client = get_client()

# ── URL-noise filter (same as create_dup_summary_page.py) ────────────────────

def is_url_noise(text: str) -> bool:
    noise_keywords = ["amazonaws.com", "X-Amz-", "prod-files-secure", "UNSIGNED-PAYLOAD"]
    if any(kw in (text or "") for kw in noise_keywords):
        return True
    t = text or ""
    t = re.sub(r'\[(?:image|video|file|bookmark|pdf)\s*:.*?\]', '', t,
               flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r'\[(?:image|video|file|bookmark|pdf)\s*:?\s*\]', '', t, flags=re.IGNORECASE)
    t = re.sub(r'https?://\S{20,}', '', t)
    t = re.sub(r'[A-Za-z0-9%_-]+=(?:[A-Za-z0-9%_/+.=-]{15,})', '', t)
    return len(t.strip()) < 80

# ── load & filter duplicates ─────────────────────────────────────────────────

all_dups = json.loads(open("data/clusters/duplicates.json", encoding="utf-8").read())
dups_24  = [d for d in all_dups if d.get("dup_date", "")[:4] >= "2024"]

class_a = [d for d in dups_24
           if not is_url_noise(d.get("dup_text", ""))
           and not is_url_noise(d.get("canonical_text", ""))]

logger.info(f"Class-A duplicates to process: {len(class_a)} chunks")
for d in class_a:
    logger.info(f"  [{d['dup_page_title']}] ({d['dup_date']}) sim={d['similarity']:.3f}"
                f" → [{d['canonical_page_title']}] ({d['canonical_date']})")

# ── Notion block builders ─────────────────────────────────────────────────────

def notion_url(page_id: str) -> str:
    return f"https://www.notion.so/{page_id.replace('-', '')}"

def build_strikethrough_blocks(dup: dict) -> list:
    """
    Returns a list of Notion blocks to append to the duplicate page:
      1. Red bold notice: "(Duplicate of: <link>)"
      2. Strikethrough gray paragraphs with the duplicate text
    """
    canonical_url   = notion_url(dup["canonical_page_id"])
    canonical_title = dup.get("canonical_page_title", dup["canonical_page_id"])
    dup_text        = dup.get("dup_text", "")

    notice = {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": "(Duplicate of: "},
                    "annotations": {"bold": True, "color": "red"},
                },
                {
                    "type": "text",
                    "text": {"content": canonical_title, "link": {"url": canonical_url}},
                    "annotations": {"bold": True, "color": "red"},
                },
                {
                    "type": "text",
                    "text": {"content": f"  {dup['canonical_date']})"},
                    "annotations": {"bold": True, "color": "red"},
                },
            ]
        },
    }

    # Split text into ≤1800-char chunks (Notion rich_text limit is 2000)
    text_blocks = []
    for i in range(0, len(dup_text), 1800):
        piece = dup_text[i:i + 1800]
        text_blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": piece},
                    "annotations": {"strikethrough": True, "color": "gray"},
                }]
            },
        })

    return [notice] + text_blocks


def build_dup_properties(dup: dict) -> dict:
    return {
        "IsDuplicate": {"checkbox": True},
        "CanonicalPage": {"url": notion_url(dup["canonical_page_id"])},
        "CanonicalChunk": {
            "rich_text": [{"type": "text", "text": {"content": dup["canonical_chunk_id"][:2000]}}]
        },
    }

# ── main ─────────────────────────────────────────────────────────────────────

def run(dry_run: bool) -> None:
    if not class_a:
        logger.info("No Class-A duplicates found. Nothing to do.")
        return

    # Group by dup page so we update properties once per page
    from collections import defaultdict
    by_page: dict[str, list] = defaultdict(list)
    for d in class_a:
        by_page[d["dup_page_id"]].append(d)

    for page_id, entries in by_page.items():
        title = entries[0]["dup_page_title"]
        date  = entries[0]["dup_date"]
        logger.info(f"\nProcessing: [{title}] ({date}) — {len(entries)} chunk(s)")

        for entry in entries:
            blocks = build_strikethrough_blocks(entry)
            props  = build_dup_properties(entry)

            logger.info(f"  chunk sim={entry['similarity']:.3f}: "
                        f"{entry.get('dup_text','')[:60].replace(chr(10),' ')}…")
            logger.info(f"  → will append {len(blocks)} blocks + update properties")

            if dry_run:
                logger.info("  [DRY-RUN] skipping actual write")
                continue

            # 1. Update page properties
            try:
                client.pages.update(page_id=page_id, properties=props)
                logger.info("  ✓ Properties updated (IsDuplicate, CanonicalPage)")
                time.sleep(0.4)
            except Exception as e:
                logger.error(f"  ✗ Failed to update properties: {e}")
                continue

            # 2. Append strikethrough blocks
            try:
                client.blocks.children.append(block_id=page_id, children=blocks)
                logger.info(f"  ✓ Appended {len(blocks)} blocks with strikethrough")
                time.sleep(0.4)
            except Exception as e:
                logger.error(f"  ✗ Failed to append blocks: {e}")

    if dry_run:
        logger.info("\n[DRY-RUN] Done. Run without --dry-run to apply changes.")
    else:
        logger.info("\nDone. Check Notion pages for strikethrough annotations.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only, do not write to Notion")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
