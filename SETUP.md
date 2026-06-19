# SETUP — BCE Legacy Tool (Windows + Claude Code GUI)

A start-to-finish checklist. You only do steps 1–4 once.

---

## 1. Unzip to the permanent folder

Unzip so the files land here (no extra nested folder):

```
D:\Data\Personal Documents\Collection\bce-legacy\
    viewer.html
    editor.html
    serve.py
    CLAUDE.md
    data\books.json
    scripts\
    ...
```

If your unzipper makes `bce-legacy\bce-legacy\...`, move the inner folder
up one level. The folder name has spaces ("Personal Documents") — that's
fine for everything here because nothing is typed by hand into a terminal
except the two commands below, and those run *inside* the folder.

---

## 2. Check Python (one time)

Open the folder, click the address bar, type `cmd`, press Enter. A terminal
opens already inside the folder. Type:

```
python --version
```

- Prints a version (e.g. `Python 3.12`) → you're set, use `python` everywhere.
- Says "not found" → try `py --version`. If THAT works, use `py` instead of
  `python` in every command below.
- Neither works → install Python from python.org, and **tick "Add Python to
  PATH"** in the installer. Then reopen the terminal.

---

## 3. Open the folder in Claude Code (GUI)

In the Claude Code desktop app: **Open Folder** →
`D:\Data\Personal Documents\Collection\bce-legacy`

Open the **folder**, not a file. Claude Code reads `CLAUDE.md` automatically,
so it starts already knowing what the project is and how the pieces fit.

First thing to type in Claude Code:

> Read CLAUDE.md, then run `python scripts/enrich_legacy.py` and show me the
> review so I can see what's seeded vs. missing.

(Use `py` instead of `python` if that's what step 2 told you.)

---

## 4. Make it a Git repo (recommended — protects your edits)

Ask Claude Code:

> Initialize a git repo here and make the first commit.

Or in the terminal:

```
git init
git add .
git commit -m "initial: BCE legacy slide tool"
```

Why: the editor and enrichment both rewrite `books.json`. Git lets you undo
a whole session if something goes sideways. (The editor also auto-backs-up
every save to `data\backups\`, so you have two safety nets.)

---

## Daily use — running the tool

In the terminal (inside the folder):

```
python serve.py
```

Leave that window open. It runs both pages:

- **Slide for OBS** → `http://localhost:8000/viewer.html`
- **Editor** → `http://localhost:8000/editor.html`

Add a **Browser source** in OBS pointing at the viewer URL (1920×1080,
transparent). Flip books with **← →**, or use `viewer.html?i=14` to pin one
book per scene.

Stop the tool with **Ctrl+C** in the terminal.

> Double-clicking viewer.html will NOT work — it shows "books.json not
> found". The pages must be served by `serve.py`. This is the #1 gotcha.

---

## Editing things that are wrong  (covers / legacy numbers / notes)

1. `python serve.py`
2. Open `http://localhost:8000/editor.html`
3. Click a book on the left. The colored dot shows its state:
   - green = range verified · amber = seeded but unverified · gray = no range
4. Fix the legacy from/to, add gaps, write pod talking points, set the cover
   path, tick "verified" when you've confirmed it.
5. **Save changes.** It writes back to `books.json` and makes a timestamped
   backup first. Refresh the viewer to see it.

No JSON editing by hand needed — but you still can (it's just a text file),
and Claude Code can edit it too.

---

## Refreshing your collection from CLZ

When you buy more books and want to refresh:

1. In CLZ Comics, export to CSV again.
2. **Drop the new file in the `bce-legacy` folder as `export_comics.csv`**
   (replace the old one — same filename).
3. In the editor, click **↻ Re-import**. That's it — it re-runs the importer
   with the right settings (stored per series) and tells you how many books
   came in. No command to type.

**Your edits survive this.** The rebuild matches books by their stable id (or
ISBN) and keeps legacy ranges, pod notes, research, manual order, and verified
flags. New books come in blank at the end; existing books keep everything.

Prefer the command line? It still works:
```
python scripts\build_books.py --csv export_comics.csv ^
    --series-group "Spider-Man: Amazing" --box "Bookshelf" ^
    --series-label "Amazing Spider-Man" --run-max 1000 ^
    --series-id asm --out data\books.json
```
(`^` continues a line in Windows cmd. Or just ask Claude Code to run it.)

## Switching characters, colors, and adding/removing books

- **Series picker** — top of the editor's left rail (and a hover menu in the
  top-left of the viewer). Pick which character you're showing.
- **Colors** — the editor's **⚙ Colors** button: set the screen background and
  accent color (color wheel, hex, or eyedropper). Saved per series so the OBS
  viewer picks it up on its next refresh. Leave the background **Transparent**
  to keep OBS keyable.
- **Add / remove / reorder** — **+ Add** makes a blank book; the selected book
  has **↑ Move up / ↓ Move down / Delete**. Order is saved and survives a
  re-import. (Changes apply when you click **Save changes**.)
- **Web research** — on a selected book, **🔎 Research this volume** looks up
  info about the collection/issues and lets you save it onto the book.

Adding a second character: export that character's shelf from CLZ to its own
CSV, then build it once with a new `--series-id` (e.g. `--series-id xmen
--out data\xmen.json`). It joins the series picker automatically.

---

## Getting covers

```
python scripts\fetch_covers.py
```

Downloads a cover for every ISBN into `covers\`. Re-run anytime; it skips
ones you already have. For a sharper cover than the API gives, drop your own
`<isbn>.jpg` into `covers\` and it won't be overwritten.

---

## Doing enhancements later

This is a normal code project, so just describe what you want to Claude Code.
Examples that fit cleanly:

- "Add a second character — here's the X-Men export. Make the viewer switch
  between characters."
- "Add a 'chonk' stat showing page count as a bar."
- "Make an overview slide that shows the whole run with all gaps at once."
- "Pull cover art from a higher-res source than Google Books."

Because data (books.json) is separate from presentation (viewer.html), most
enhancements touch only one of them. Commit to Git before big changes.

---

## Quick reference

| Task | Command |
|---|---|
| Run viewer + editor | `python serve.py` |
| Refresh from CLZ | `python scripts\build_books.py --csv export_comics.csv --series-group "Spider-Man: Amazing" --box "Bookshelf" --out data\books.json` |
| Review enrichment progress | `python scripts\enrich_legacy.py` |
| Get covers | `python scripts\fetch_covers.py` |
| Viewer (flip) | `localhost:8000/viewer.html` |
| Viewer (pin book 14) | `localhost:8000/viewer.html?i=14` |
| Editor | `localhost:8000/editor.html` |
