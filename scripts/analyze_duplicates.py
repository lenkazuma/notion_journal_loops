"""Analyze duplicate detection results and show year distribution."""
import json, sys, collections
sys.path.insert(0, ".")

dups = json.loads(open("data/clusters/duplicates.json", encoding="utf-8").read())
print(f"Total duplicates: {len(dups)}")

# Year distribution
by_year = collections.Counter()
for d in dups:
    year = d.get("dup_date", "")[:4]
    by_year[year] += 1
print("\nBy dup year:")
for y, c in sorted(by_year.items()):
    print(f"  {y}: {c}")

# 2024+ only
dups_24 = [d for d in dups if d.get("dup_date", "")[:4] >= "2024"]
print(f"\n2024+ duplicates: {len(dups_24)}")

# Group by dup page
by_page = collections.defaultdict(list)
for d in dups_24:
    by_page[d["dup_page_title"]].append(d)

print(f"\nAffected pages (2024+): {len(by_page)}")
for title, entries in sorted(by_page.items(), key=lambda x: x[1][0].get("dup_date","")):
    dates = set(e["dup_date"] for e in entries)
    can_titles = set(e["canonical_page_title"] for e in entries)
    sims = [e["similarity"] for e in entries]
    print(f"  [{title}] {min(dates)} | {len(entries)} chunks | canonical: {can_titles} | sim: {max(sims):.3f}")
