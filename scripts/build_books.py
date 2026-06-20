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

# Fields carried over from a prior build so a CSV refresh never loses manual work.
PRESERVE_FIELDS = ("id", "order", "legacy_from", "legacy_to",
                   "gaps_avail", "also_in", "pod", "research", "verified")

def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", clean(s).lower()).strip("-")
    return s[:40] or "book"

def load_existing(path):
    """Preserve id/order/enrichment from a prior build so rebuilds don't lose work.
    Returns (by_isbn, by_composite, dup_isbns, empty_isbn_count). Unique ISBNs match
    reliably; duplicate/empty ISBNs fall back to an (isbn, title, era) composite and are
    reported so the user knows those may not round-trip cleanly."""
    if not os.path.exists(path):
        return {}, {}, [], 0
    try:
        with open(path, encoding="utf-8") as f:
            prev = json.load(f)
    except Exception:
        return {}, {}, [], 0
    prev_books = prev.get("books", [])
    counts = {}
    for b in prev_books:
        i = clean(b.get("isbn"))
        if i:
            counts[i] = counts.get(i, 0) + 1
    by_isbn, by_comp, empty = {}, {}, 0
    for b in prev_books:
        rec = {k: b.get(k) for k in PRESERVE_FIELDS if k in b}
        i = clean(b.get("isbn"))
        by_comp[(i, clean(b.get("title")), clean(b.get("era_tag")))] = rec
        if i and counts[i] == 1:
            by_isbn[i] = rec
        if not i:
            empty += 1
    dup_isbns = sorted(i for i, c in counts.items() if c > 1)
    return by_isbn, by_comp, dup_isbns, empty

def upsert_manifest(args):
    """Record this series in data/series.json so the viewer/editor can list it and
    serve.py can whitelist its save target. Preserves an existing theme block."""
    man_path = os.path.join(os.path.dirname(args.out) or ".", "series.json")
    manifest = []
    if os.path.exists(man_path):
        try:
            with open(man_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = []
    entry = {
        "id": args.series_id,
        "label": args.series_label or args.series_group,
        "file": os.path.basename(args.out),
        "csv": os.path.basename(args.csv),       # which CLZ export feeds this series (for re-import)
        "series_group": args.series_group,
        "box": args.box,
        "run_max": args.run_max,
        "theme": {},
    }
    for e in manifest:
        if e.get("id") == args.series_id:
            entry["theme"] = e.get("theme", {})   # keep the user's chosen palette
            e.clear(); e.update(entry)
            break
    else:
        manifest.append(entry)
    with open(man_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Updated {man_path}: series '{args.series_id}' -> {entry['file']}")

def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # so it runs from any folder
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--series-group", required=True)
    ap.add_argument("--box", required=True)
    ap.add_argument("--out", default="data/books.json")
    ap.add_argument("--run-max", type=int, default=1000,
                    help="right end of the legacy ruler")
    ap.add_argument("--series-label", default=None,
                    help="header label; defaults to the series group")
    ap.add_argument("--series-id", default=None,
                    help="stable id for this series (e.g. asm); writes the data/series.json manifest")
    args = ap.parse_args()

    by_isbn, by_comp, dup_isbns, empty_isbn = load_existing(args.out)

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
            "id": None,            # stable identity; assigned below, preserved across rebuilds
            "order": None,         # manual shelf order; preserved across rebuilds
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
            # --- enrichment fields (filled by enrich_legacy.py / editor) ---
            "legacy_from": None,
            "legacy_to": None,
            "gaps_avail": [],
            "also_in": "",
            "pod": "",
            "research": [],
            "verified": False,
        }
        # preserve id/order/enrichment from the prior build (unique ISBN, else composite)
        comp = (isbn, title, clean(r.get("Issue")))
        rec = by_isbn.get(isbn) if (isbn and isbn in by_isbn) else by_comp.get(comp)
        if rec:
            book["id"] = rec.get("id")
            book["order"] = rec.get("order")
            book.update({k: v for k, v in rec.items()
                         if k not in ("id", "order") and v not in (None, "", [])})
        books.append(book)

    # assign/repair stable ids: keep a valid unique id, otherwise fill it in. This also
    # breaks duplicates — a composite match on duplicate ISBNs can preserve the same id
    # onto two books, and ids must stay unique within the series.
    seen_ids = set()
    for b in books:
        bid = b.get("id")
        if bid and bid not in seen_ids:
            seen_ids.add(bid)
            continue
        base = b["isbn"] if b["isbn"] else slug(b["title"])
        cand, n = base, 2
        while cand in seen_ids:
            cand = f"{base}-{n}"; n += 1
        b["id"] = cand
        seen_ids.add(cand)

    # ordering: a preserved manual order wins; brand-new books fall in by era at the end;
    # then renumber to gapped 10/20/30 by final position (keeps gaps for future inserts).
    INF = float("inf")
    if any(b.get("order") is not None for b in books):
        books.sort(key=lambda b: (b["order"] if b.get("order") is not None else INF,
                                  era_sort_key(b["era_tag"], b["year"]), b["year"] or 9999, b["id"]))
    else:
        books.sort(key=lambda b: (era_sort_key(b["era_tag"], b["year"]), b["year"] or 9999, b["id"]))
    for i, b in enumerate(books):
        b["order"] = (i + 1) * 10

    out = {
        "series": args.series_label or args.series_group,
        "run_max": args.run_max,
        "count": len(books),
        "books": books,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    if args.series_id:
        upsert_manifest(args)

    enriched = sum(1 for b in books if b["legacy_from"] is not None)
    print(f"Wrote {args.out}: {len(books)} books "
          f"({enriched} with legacy ranges, {len(books)-enriched} need enrichment)")
    if dup_isbns:
        print(f"  WARNING: duplicate ISBNs in prior data {dup_isbns} — enrichment for these is "
              f"matched by title+era, not ISBN alone; verify they round-tripped.")
    if empty_isbn:
        print(f"  NOTE: {empty_isbn} book(s) had no ISBN; matched by title+era and given a slug id.")

if __name__ == "__main__":
    main()
