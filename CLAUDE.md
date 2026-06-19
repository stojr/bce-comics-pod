# CLAUDE.md — BCE Comics Pod: Legacy Slide Tool

## What this project is
A data-driven slide generator for the **BCE Comics Pod**. For a given
character (e.g. Amazing Spider-Man), it shows one collected edition per
slide — what's on Stephen's bookshelf, what legacy issues it covers, where
it sits in the full legacy run (heading toward #1000), gaps, alternate
formats, and pod talking points. Rendered as a transparent HTML browser
source in OBS.

The hosts are Stephen (Stojr's Shelf) and Nick. Slides need room for them
to talk, so each slide has a dedicated "pod talking points" area.

## How it works (data flow)
```
export_comics.csv          CLZ Comics export (raw, all 11k+ issues)
   │  build_books.py        filter to one shelf + map formats + order
   ▼
data/books.json            the 60 shelf books, seeded
   │  enrich_legacy.py      add legacy_from/legacy_to/gaps  (the lookup)
   │  fetch_covers.py       download covers/<isbn>.jpg by ISBN
   ▼
viewer.html                OBS browser source — arrow keys or ?i=N
```

## Key facts about the data
- Source: CLZ Comics (https://clz.com/comics) CSV export.
- Filter for ASM shelf: `Series Group == "Spider-Man: Amazing"` AND
  `Storage Box == "Bookshelf"` → 60 books.
- The CSV has title, format, year, **ISBN-13 (Barcode column)**, pages,
  read status. It does NOT have legacy issue ranges — those are looked up.
- `Format` is already taxonomized; build_books.py maps it (Epic Collection,
  Epic Collection: Modern → "Modern Era Epic", Omni → "Omnibus", etc.).
- `run_max` in books.json = right end of the ruler (1000 for ASM).

## The enrichment job (most important open task)
Each book needs `legacy_from` / `legacy_to` (the legacy issue range it
collects). 17 Epic Collections are pre-seeded but flagged
`verified: false`. The rest are null.

**To enrich:** for each book with `verified: false` or `legacy_from: null`,
look up which ASM legacy issues it collects (web search by ISBN or title +
"collects issues"), then either edit books.json directly or call:
```
python scripts/enrich_legacy.py --isbn <isbn> --from <a> --to <z> --verified
python scripts/enrich_legacy.py --isbn <isbn> --gap <a> <z>      # available-but-unowned gap
python scripts/enrich_legacy.py --isbn <isbn> --pod "talking point · another"
python scripts/enrich_legacy.py --isbn <isbn> --also "Omnibus Vol. 2"
```
Run `python scripts/enrich_legacy.py` with no args for a review of progress.

## Running the viewer + editor
Browsers block fetch() of local json over file://, AND the editor needs to
write books.json back, so use serve.py (not bare http.server):
```
python serve.py
```
Then:
```
http://localhost:8000/viewer.html          (arrow keys to flip)
http://localhost:8000/viewer.html?i=14      (jump to book 14 — one per scene)
http://localhost:8000/editor.html           (point-and-click edit + save)
```
Viewer keys: ← → flip · R read/unread filter · S jump to next unverified.

The editor lets Stephen fix legacy ranges, gaps, pod notes, cover paths, and
the verified flag without touching JSON. Every save POSTs to serve.py, which
backs up to data/backups/ before writing. Stephen edits by hand sometimes;
keep books.json human-readable (indent=2).

## Adding a new character later
1. In CLZ, set that character's Series Group + a shelf storage box.
2. Re-export, replace export_comics.csv.
3. `python scripts/build_books.py --csv export_comics.csv
   --series-group "<Group>" --box "Bookshelf"
   --series-label "<Display Name>" --run-max <N> --out data/<char>.json`
4. Enrich + fetch covers, point viewer at the new json (it currently loads
   data/books.json — parameterize if you keep several characters).

## Conventions
- Keep books.json the single source of truth; never hand-edit the viewer
  for content.
- `verified: true` means a human confirmed the range; seeds are false.
- Covers are named by ISBN so they survive rebuilds.
