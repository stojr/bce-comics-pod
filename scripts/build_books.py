#!/usr/bin/env python3
"""
build_books.py — convert a CLZ Comics CSV export into books.json for the
BCE Legacy Slide viewer.

WHAT IT DOES
  - Reads the raw CLZ export CSV.
  - Filters to one character's shelf using SERIES_GROUP + STORAGE_BOX.
  - Maps CLZ "Format" values to the show's slide categories.
  - Orders books by legacy era (using the CLZ "Issue" era tag + release year).
  - Emits data/books.json with everything the viewer needs EXCEPT the legacy
    issue ranges + gaps, which are added later by enrich_legacy.py.

USAGE
  python scripts/build_books.py \
      --csv export_comics.csv \
      --series-group "Spider-Man: Amazing" \
      --box "Bookshelf" \
      --out data/books.json

  Re-run any time you add books in CLZ and re-export. It PRESERVES any
  manual legacy ranges already in an existing books.json (matched by ISBN),
  so you never lose enrichment work on a rebuild.
"""

import argparse, json, csv, sys, os, re

# CLZ Format string -> (slide category, goes_on_spine?)
FORMAT_MAP = {
    "Epic Collection":          ("Epic Collection", True),
    "Epic Collection: Modern":  ("Modern Era Epic", True),
    "Omni":                     ("Omnibus", True),
    "Hardcover":                ("Hardcover", True),
    "Hardcover (Slipcase)":     ("Hardcover", True),
    "Masterworks":              ("Masterworks", True),
    "Thick Trade":              ("Complete Collection", True),
    "Trade Paperback":          ("Trade Paperback", True),
    "Treasury":                 ("Treasury", True),
    "Graphic Novel":            ("Graphic Novel", True),
    "DC Finest":                ("DC Finest", True),
    "B&W: Essential Ed":        ("Essential", True),
    "Compact":                  ("Compact", True),
}

def clean(v):
    if v is None: return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s

def era_sort_key(issue, release_year):
    """Best-effort chronological key from the CLZ 'Issue' era tag.
    The era tag is often the original publication year (1963, 1964...).
    Falls back to release year of the book itself."""
    s = clean(issue)
    m = re.search(r"(19|20)\d{2}", s)
    if m:
        return int(m.group(0))
    try:
        return int(float(release_year))
    except (ValueError, TypeError):
        return 9999

def load_existing_legacy(path):
    """Preserve manual legacy ranges from a prior build, keyed by ISBN."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            prev = json.load(f)
    except Exception:
        return {}
    keep = {}
    for b in prev.get("books", []):
        isbn = b.get("isbn")
        if isbn and (b.get("legacy_from") is not None or b.get("verified")):
            keep[isbn] = {
                "legacy_from": b.get("legacy_from"),
                "legacy_to":   b.get("legacy_to"),
                "gaps_avail":  b.get("gaps_avail", []),
                "also_in":     b.get("also_in", ""),
                "pod":         b.get("pod", ""),
                "verified":    b.get("verified", False),
            }
    return keep

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--series-group", required=True)
    ap.add_argument("--box", required=True)
    ap.add_argument("--out", default="data/books.json")
    ap.add_argument("--run-max", type=int, default=1000,
                    help="right end of the legacy ruler")
    ap.add_argument("--series-label", default=None,
                    help="header label; defaults to the series group")
    args = ap.parse_args()

    existing = load_existing_legacy(args.out)

    rows = []
    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if clean(r.get("Series Group")) == args.series_group \
               and clean(r.get("Storage Box")) == args.box:
                rows.append(r)

    books = []
    for r in rows:
        fmt_raw = clean(r.get("Format"))
        cat, spine = FORMAT_MAP.get(fmt_raw, (fmt_raw or "Other", True))
        isbn = clean(r.get("Barcode"))
        title = clean(r.get("Full Title")) or clean(r.get("Title")) or "(title needs lookup)"
        try:
            ry = int(float(r.get("Release Year"))) if clean(r.get("Release Year")) else None
        except (ValueError, TypeError):
            ry = None
        try:
            pages = int(float(r.get("No. of Pages"))) if clean(r.get("No. of Pages")) else None
        except (ValueError, TypeError):
            pages = None

        book = {
            "title": title,
            "format": cat,
            "format_raw": fmt_raw,
            "on_spine": spine,
            "year": ry,
            "era_tag": clean(r.get("Issue")),
            "isbn": isbn,
            "pages": pages,
            "read": clean(r.get("Read")).lower() == "yes",
            "status": "owned",
            "cover": f"covers/{isbn}.jpg" if isbn else "",
            # --- enrichment fields (filled by enrich_legacy.py) ---
            "legacy_from": None,
            "legacy_to": None,
            "gaps_avail": [],
            "also_in": "",
            "pod": "",
            "verified": False,
        }
        # merge preserved enrichment
        if isbn in existing:
            book.update({k: v for k, v in existing[isbn].items() if v not in (None, "", [])})
        books.append(book)

    books.sort(key=lambda b: (era_sort_key(b["era_tag"], b["year"]), b["year"] or 9999))

    out = {
        "series": args.series_label or args.series_group,
        "run_max": args.run_max,
        "count": len(books),
        "books": books,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    enriched = sum(1 for b in books if b["legacy_from"] is not None)
    print(f"Wrote {args.out}: {len(books)} books "
          f"({enriched} with legacy ranges, {len(books)-enriched} need enrichment)")

if __name__ == "__main__":
    main()
