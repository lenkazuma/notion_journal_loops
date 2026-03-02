"""Build detailed duplicate report data for Notion page creation."""
import json, sys, collections
sys.path.insert(0, ".")

dups = json.loads(open("data/clusters/duplicates.json", encoding="utf-8").read())

# Filter 2024+
dups_24 = [d for d in dups if d.get("dup_date", "")[:4] >= "2024"]

# Build per-pair detail: for each (dup_page, canonical_page) pair, show chunk previews
pairs = {}
for d in dups_24:
    key = (d["dup_page_id"], d["canonical_page_id"])
    if key not in pairs:
        pairs[key] = {
            "dup_title": d["dup_page_title"],
            "dup_date": d["dup_date"],
            "dup_page_id": d["dup_page_id"],
            "canonical_title": d["canonical_page_title"],
            "canonical_date": d["canonical_date"],
            "canonical_page_id": d["canonical_page_id"],
            "chunks": [],
        }
    pairs[key]["chunks"].append({
        "dup_chunk_id": d["dup_chunk_id"],
        "canonical_chunk_id": d["canonical_chunk_id"],
        "similarity": d["similarity"],
        "dup_text_preview": d.get("dup_text", "")[:120].replace("\n", " "),
        "canonical_text_preview": d.get("canonical_text", "")[:120].replace("\n", " "),
    })

# Sort by dup_date
sorted_pairs = sorted(pairs.values(), key=lambda x: x["dup_date"])

print(f"Unique page-pairs (2024+): {len(sorted_pairs)}")
for p in sorted_pairs:
    print(f"\n  [{p['dup_title']}] ({p['dup_date']}) → canonical: [{p['canonical_title']}] ({p['canonical_date']})")
    print(f"  chunks: {len(p['chunks'])}, max_sim: {max(c['similarity'] for c in p['chunks']):.4f}")
    for c in p["chunks"][:2]:
        print(f"    sim={c['similarity']:.3f} | {c['dup_text_preview'][:80]}...")

# Save for Notion writer
with open("data/outputs/dup_pairs_2024plus.json", "w", encoding="utf-8") as f:
    json.dump(sorted_pairs, f, ensure_ascii=False, indent=2)
print("\nSaved to data/outputs/dup_pairs_2024plus.json")
