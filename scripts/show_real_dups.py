"""Show actual text content of real duplicate pairs (2024+, non-image)."""
import json, sys, re, pathlib
sys.path.insert(0, ".")

def is_image(text):
    non_media = re.sub(r'\[(?:image|video|file|bookmark|pdf):[^\]]*\]', '', text or '').strip()
    non_media = re.sub(r'https?://[^\s]+amazonaws\.com[^\s]*', '', non_media).strip()
    return len(non_media) < 50

def load_text(pid):
    p = pathlib.Path(f"data/raw/pages/{pid}.json")
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")).get("raw_text", "")
    return ""

dups = json.loads(open("data/clusters/duplicates.json", encoding="utf-8").read())
dups_24 = [d for d in dups if d.get("dup_date", "")[:4] >= "2024"]

shown = set()
for d in dups_24:
    can_text = load_text(d["canonical_page_id"])
    dup_text_full = load_text(d["dup_page_id"])
    if is_image(can_text) or is_image(dup_text_full):
        continue
    key = (d["dup_page_title"], d["canonical_page_title"])
    if key in shown:
        continue
    shown.add(key)
    print(f"DUP : [{d['dup_page_title']}] {d['dup_date']}")
    print(f"CAN : [{d['canonical_page_title']}] {d['canonical_date']}")
    print(f"sim : {d['similarity']:.4f}")
    print(f"DUP text: {d.get('dup_text','')[:200]}")
    print(f"CAN text: {d.get('canonical_text','')[:200]}")
    print("-" * 60)
