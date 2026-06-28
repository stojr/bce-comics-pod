# BCE Legacy Slide Tool

One slide per collected edition for the BCE Comics Pod — what's on the
shelf, what legacy issues it covers, where it sits in the run toward #1000,
gaps, alternate formats, BCE Pod coverage + ratings, and room for you and
Nick to talk. Driven by your CLZ Comics export. Rendered as a transparent
HTML browser source in OBS.

## View it online (read-only)

The viewer is a static page, published via **GitHub Pages** — no server needed:

- **Slide:** `viewer.html`
- Pick a series: `viewer.html?series=ff` (asm, ff, wca, …)
- Pin one book per OBS scene: `viewer.html?series=ff&i=14`

Viewer hotkeys: **← →** prev/next · **C** hide/show the issue-cover wall ·
**R** read/unread filter · **S** jump to next unverified range.

## Edit it (local only)

Editing needs the local server (browsers can't write files), so it is **not**
on the public site. New here? Read **SETUP.md** — a Windows + Claude Code checklist.

```bash
# run the viewer AND the editor (one command)
python serve.py
#   slide  → http://localhost:8000/viewer.html
#   editor → http://localhost:8000/editor.html
```

The editor handles legacy ranges, gaps, pod talking points, **BCE Pod coverage
& ratings**, covers (pick by file), per-issue cover fix-ups, and creating a
**new series**. Every save backs up to `data/backups/` first.

**Workflow:** edit locally → `git commit` → `git push` → the public viewer updates.

## Driving it in OBS

Add a **Browser** source, 1920×1080, transparent background, pointed at the
published `viewer.html` (or the local one). Flip live with **← →** (focus the
source, or keep an off-screen browser window focused), or make one Browser
source per scene with `?series=…&i=…` for a pre-built rundown.

## Enriching legacy ranges (the one manual-ish step)

Your CSV doesn't contain the legacy issue range each book covers, so that gets
looked up once — in the editor, or via the CLI:

```bash
python scripts/enrich_legacy.py --isbn 9780785188346 --from 1 --to 17 --verified
python scripts/enrich_legacy.py --isbn 9780785188346 --pod "First Sinister Six · Ditko run"
```

## Setup (fresh clone)

1. Python 3 — standard library only, no pip installs.
2. Copy `secrets.local.example.json` → `secrets.local.json` and add a free
   [Comic Vine API key](https://comicvine.gamespot.com/api/). Only needed to fetch covers.
3. `python serve.py`

## Files
```
export_comics.csv     your CLZ export (replace to refresh)
data/<id>.json        books for one series (asm, ff, wca, …)
data/series.json      manifest: which series exist, labels, run_max, theme
data/backups/         timestamped auto-backups (every editor save)   [gitignored]
covers/               cover art + per-issue thumbnails (committed for Pages)
secrets.local.json    your Comic Vine key                            [gitignored]
viewer.html           the OBS slide                editor.html       the editor
serve.py              runs viewer + editor + saves (one command)
scripts/
  build_books.py      CSV → data/<id>.json
  enrich_legacy.py    add/review legacy ranges + gaps + pod notes (CLI)
  fetch_issue_covers.py   per-issue cover thumbnails (pinned Comic Vine volumes)
  comic_cover_fetch.py    Comic Vine lookup module
SETUP.md              Windows + Claude Code walkthrough
CLAUDE.md             project context for Claude Code
```
