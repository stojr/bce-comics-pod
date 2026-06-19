# BCE Legacy Slide Tool

One slide per collected edition for the BCE Comics Pod — what's on the
shelf, what legacy issues it covers, where it sits in the run, and room
for you and Nick to talk. Driven by your CLZ Comics export.

## Quick start

New here? Read **SETUP.md** — it's a Windows + Claude Code GUI checklist.

```bash
# run the viewer AND the editor (one command)
python serve.py
#   slide  → http://localhost:8000/viewer.html
#   editor → http://localhost:8000/editor.html

# get covers by ISBN (needs internet)
python scripts/fetch_covers.py

# refresh from a new CLZ export (your edits survive — matched by ISBN)
python scripts/build_books.py --csv export_comics.csv \
    --series-group "Spider-Man: Amazing" --box "Bookshelf" \
    --series-label "Amazing Spider-Man" --out data/books.json
```

## Driving it in OBS

Add a **Browser** source, 1920×1080, transparent background:

- `http://localhost:8000/viewer.html` — flip live with **← →** arrow keys
  (interact with the source, or keep an off-screen browser window focused).
- `http://localhost:8000/viewer.html?i=14` — pin one specific book; make
  one Browser source per scene this way for a pre-built rundown.

Viewer hotkeys: **← →** prev/next · **R** read/unread filter ·
**S** jump to next unverified range.

## Enriching legacy ranges (the one manual-ish step)

Your CSV doesn't contain the legacy issue range each book covers, so that
gets looked up once. Easiest path: open this folder in **Claude Code** and
ask it to look up the unverified ranges by ISBN/title, then verify. Or set
them by hand:

```bash
python scripts/enrich_legacy.py --isbn 9780785188346 --from 1 --to 17 --verified
python scripts/enrich_legacy.py --isbn 9780785188346 --pod "First Sinister Six · Ditko run"
```

17 Epic Collections are pre-seeded (flagged unverified) so the ruler isn't
empty on day one. Everything else shows "range not yet looked up."

## Files
```
export_comics.csv     your CLZ export (replace to refresh)
data/books.json       single source of truth (60 books)
data/backups/         timestamped auto-backups (made on every editor save)
covers/<isbn>.jpg     downloaded cover art
viewer.html           the OBS slide
editor.html           point-and-click editor for ranges/covers/notes
serve.py              runs viewer + editor + handles saves (one command)
scripts/
  build_books.py      CSV → books.json
  enrich_legacy.py    add/review legacy ranges + gaps + pod notes (CLI)
  fetch_covers.py     download covers by ISBN
SETUP.md              Windows + Claude Code GUI walkthrough
CLAUDE.md             project context for Claude Code
```
