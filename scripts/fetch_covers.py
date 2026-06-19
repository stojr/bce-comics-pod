#!/usr/bin/env python3
"""
fetch_covers.py — download a cover image for each book by ISBN.

Runs on YOUR PC (needs internet). Reads data/books.json, fetches a cover
for every book that has an ISBN and doesn't already have covers/<isbn>.jpg,
and saves it there. The viewer references covers/<isbn>.jpg automatically.

Primary source: Google Books API (no key needed for cover thumbnails).
You already have an isbn-lookup MCP built on the same API — this is the
plain-HTTP equivalent so it runs unattended.

USAGE
  python scripts/fetch_covers.py
  python scripts/fetch_covers.py --force      # re-download everything
  python scripts/fetch_covers.py --isbn 9780785188346   # just one

NOTE
  Google Books thumbnails are small (~128px wide). For crisp 1080p slides
  you may want higher-res art. Two upgrades, in order of effort:
    1. Swap COVER_SOURCES to add openlibrary covers (size 'L').
    2. For Marvel-accurate trade dress, drop a hi-res jpg into covers/
       named <isbn>.jpg by hand — the fetcher won't overwrite it unless
       you pass --force.
"""
import argparse, json, os, sys, time, urllib.request, urllib.parse

COVERS_DIR = "covers"
DATA = "data/books.json"

def google_books_cover(isbn):
    url = "https://www.googleapis.com/books/v1/volumes?q=isbn:" + urllib.parse.quote(isbn)
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            j = json.load(r)
    except Exception as e:
        return None
    items = j.get("items") or []
    if not items: return None
    img = (items[0].get("volumeInfo",{}).get("imageLinks") or {})
    # prefer the largest available
    for k in ("extraLarge","large","medium","thumbnail","smallThumbnail"):
        if k in img:
            return img[k].replace("http://","https://").replace("&edge=curl","")
    return None

def openlibrary_cover(isbn):
    # Large size; returns a 1x1 pixel if missing, so caller should sanity-check size
    return f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"

COVER_SOURCES = [google_books_cover, openlibrary_cover]

def download(url, path):
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"BCE-Pod/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if len(data) < 1500:   # openlibrary "missing" placeholder is tiny
            return False
        with open(path,"wb") as f: f.write(data)
        return True
    except Exception:
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--isbn", default=None)
    args = ap.parse_args()
    os.makedirs(COVERS_DIR, exist_ok=True)
    d = json.load(open(DATA, encoding="utf-8"))

    targets = [b for b in d["books"] if b.get("isbn")]
    if args.isbn:
        targets = [b for b in targets if b["isbn"]==args.isbn]

    got=skip=miss=0
    for b in targets:
        isbn=b["isbn"]; path=os.path.join(COVERS_DIR, isbn+".jpg")
        if os.path.exists(path) and not args.force:
            skip+=1; continue
        url=None
        for src in COVER_SOURCES:
            url=src(isbn)
            if url and download(url, path):
                print(f"  ✓ {isbn}  {b['title'][:40]}")
                got+=1; break
        else:
            print(f"  ✗ {isbn}  {b['title'][:40]}  (no cover found)")
            miss+=1
        time.sleep(0.4)   # be polite to the APIs
    print(f"\nCovers: {got} downloaded, {skip} already present, {miss} missing")

if __name__ == "__main__":
    main()
