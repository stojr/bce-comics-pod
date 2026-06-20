"""
comic_cover_fetch.py
=====================
Self-contained Comic Vine cover-image fetch + download + local-match module.

Extracted from the BCE Comics Pod video pipeline (bce_video_converter_v3.3.py)
and rewritten with ZERO project dependencies so it can be dropped into any
Python project. Standard library only -- no pip installs required.

WHAT IT DOES
------------
Given a comic series name and issue number, it will:
  1. Query the Comic Vine API for the correct volume (series).
  2. Pull the specific issue and return its cover image URL + synopsis.
  3. Download the cover image to a local folder with a normalized filename.
  4. Match an already-downloaded cover to a new request (avoid re-downloading).

It also supports collected editions (TPB / Epic Collection / Omnibus) where
there is no single issue number -- it searches volumes by name + subtitle.

QUICK START
-----------
    from comic_cover_fetch import get_cover

    path = get_cover("Uncanny X-Men", "202", covers_dir="covers")
    # -> downloads to covers/Uncanny X-Men-202.jpg and returns the path
    #    (or returns the existing local file if already downloaded)

    # Just the metadata, no download:
    synopsis, cover_url = fetch_comic_synopsis(series="Avengers", issue_num="289")

API KEY
-------
Comic Vine requires a free API key (https://comicvine.gamespot.com/api/).
A working key is hardcoded below as the default. To use your own, pass
api_key=... to any function, or set the COMIC_VINE_API_KEY env var.

Comic Vine rate limit: ~200 requests/resource per hour. Cache aggressively;
this module's local-match step (find_local_cover) avoids repeat downloads.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Default Comic Vine API key. Override per-call or via env var COMIC_VINE_API_KEY.
DEFAULT_CV_API_KEY = "87866720d057b811d827d8f128943d76769001e4"

CV_BASE = "https://comicvine.gamespot.com/api"

# Per-series volume-id cache (series name -> (volume_id, volume_name)), populated during
# a run so batch single-issue fetches don't re-search the volume every time.
_VOL_CACHE = {}

# Comic Vine BLOCKS requests with no/!generic User-Agent. A descriptive UA is REQUIRED.
USER_AGENT = "ComicCoverFetch/1.0 (+https://example.com)"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Deck/description prefixes that mark a result as a collection rather than an issue.
COLLECTION_MARKERS = ("translates", "collects", "reprints", "collecting", "includes issues")


def _log(msg: str, level: str = "info") -> None:
    """Minimal logger. Replace with your project's logger if desired."""
    print(f"[cover:{level}] {msg}")


def _resolve_key(api_key: str | None) -> str:
    return (api_key or os.environ.get("COMIC_VINE_API_KEY") or DEFAULT_CV_API_KEY).strip()


# --------------------------------------------------------------------------
# HTTP / text helpers
# --------------------------------------------------------------------------

def _fetch_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"&#\d+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str, max_chars: int = 1500) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3].rsplit(" ", 1)[0] + "..."


def _norm(text: str) -> str:
    """Lowercase, strip hyphens/punctuation, collapse spaces (for fuzzy scoring)."""
    text = text.lower()
    text = re.sub(r"[-/]", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _word_overlap(a: str, b: str) -> int:
    stop = {"the", "a", "an", "of", "in", "and", "or"}
    wa = set(_norm(a).split()) - stop
    wb = set(_norm(b).split()) - stop
    return len(wa & wb)


# Collected-edition keywords. A book titled e.g. "Vision Quest" exists as both a
# plain trade AND an Epic Collection that collect DIFFERENT issues — matching the
# edition keeps the lookup on the right one.
EDITIONS = ("epic collection", "omnibus", "complete collection", "masterworks",
            "compendium", "compact", "modern era epic")

def _edition_of(text: str) -> str:
    """Canonical edition keyword found in a format/title string, or '' (plain trade).
    'Modern Era Epic' normalizes to 'epic collection' (Comic Vine labels both 'Epic')."""
    t = _norm(text or "")
    for e in EDITIONS:
        if e in t:
            return "epic collection" if e == "modern era epic" else e
    return ""


# --------------------------------------------------------------------------
# Local cover matching (avoids re-downloading)
# --------------------------------------------------------------------------

def extract_issue_key(filename: str) -> str | None:
    """
    Normalize a filename or label into a 'title+number' match key.

      'Uncanny X-Men-202.png'  -> 'uncannyxmen202'
      'Avengers 289'           -> 'avengers289'
      'Amazing-Spider-Man-394.jpg' -> 'amazingspiderman394'

    Strips spaces, hyphens, underscores and punctuation; lowercases everything.
    """
    stem = Path(filename).stem
    for suffix in ("BCE Comics Pod One Shot BONUS", "BCE Comics Pod One Shot", "Cover"):
        stem = stem.replace(suffix, "")
    key = re.sub(r"[^a-z0-9]+", "", stem.lower())
    return key or None


def find_local_cover(series: str, issue_num: str, covers_dir: str | Path) -> str | None:
    """
    Look in covers_dir for an already-downloaded cover matching series+issue.
    Returns the file path, or None. Uses exact key match then containment fallback.
    """
    covers_dir = Path(covers_dir)
    if not covers_dir.exists():
        return None

    want = extract_issue_key(f"{series} {issue_num}")
    if not want:
        return None

    covers = [c for c in covers_dir.iterdir() if c.suffix.lower() in IMAGE_EXTS]

    # Exact match first
    for c in covers:
        if extract_issue_key(c.name) == want:
            return str(c)

    # Containment fallback (handles annual/bonus naming), prefer longest overlap
    best, best_len = None, 0
    for c in covers:
        ck = extract_issue_key(c.name)
        if not ck:
            continue
        if ck in want and len(ck) > best_len:
            best, best_len = str(c), len(ck)
        elif want in ck and len(want) > best_len:
            best, best_len = str(c), len(want)
    return best


# --------------------------------------------------------------------------
# Comic Vine API: synopsis + cover URL
# --------------------------------------------------------------------------

def fetch_comic_synopsis(
    series: str = "",
    issue_num: str = "",
    collection: str = "",
    issue_title: str = "",
    api_key: str | None = None,
    edition: str = "",
) -> tuple[str, str]:
    """
    Fetch (synopsis_text, cover_url) from Comic Vine. Either may be "" on failure.

    SINGLE ISSUE (pass series + issue_num):
      1. /search?resources=volume  -> find the series volume (best word-overlap).
      2. /issues?filter=volume:<id>,issue_number:<n>  -> the exact issue.
      3. Return cover URL (super_url > medium_url) + description/deck.

    COLLECTED EDITION (pass collection and/or issue_title, no issue_num):
      Strips 'Epic Collection / Omnibus / Vol N' boilerplate, searches volumes
      by 'series + subtitle', returns the TPB's own cover + description.
    """
    key = _resolve_key(api_key)

    is_single = bool(series and issue_num)
    is_collection = not is_single and bool(collection or issue_title)
    if not is_single and not is_collection:
        return ("", "")

    try:
        # ---- COLLECTED EDITION ----
        if is_collection:
            # Which edition are we after? Caller passes the book's format explicitly,
            # else we detect it from the collection string. A plain trade -> "" (no bias).
            edition_kw = _edition_of(edition) or _edition_of(collection)
            coll_clean = re.sub(
                r"\b(Epic Collection|Omnibus|Masterworks|Visionaries|Classic|"
                r"Complete|Ultimate|Modern Era|By The|Vol\.?|Volume|v\d+)\b",
                "", collection, flags=re.IGNORECASE,
            )
            coll_clean = re.sub(r"\s*\d+\s*$", "", coll_clean).strip()
            base_query = " ".join(p for p in (coll_clean, issue_title) if p)
            if not base_query:
                return ("", "")
            # Include the edition in the search so Comic Vine surfaces the right printing.
            query = (base_query + " " + edition_kw).strip() if edition_kw else base_query

            vol_url = (
                f"{CV_BASE}/search/?api_key={key}&format=json"
                f"&query={urllib.parse.quote(query)}&resources=volume"
                f"&field_list=id,name,description,deck,image&limit=10"
            )
            volumes = _fetch_json(vol_url).get("results", [])
            if not volumes:
                _log(f"no collection found for '{query}'", "warn")
                return ("", "")

            def _score(v):
                name = v.get("name", "")
                s = _word_overlap(base_query, name)
                if edition_kw and edition_kw in _norm(name):
                    s += 5                          # strongly prefer the matching edition
                elif edition_kw and any(e in _norm(name) for e in EDITIONS if e != edition_kw):
                    s -= 1                           # a different named edition is likely wrong
                return s
            best = max(volumes, key=_score)
            _log(f"collection match: '{best.get('name', '?')}'"
                 + (f" [want: {edition_kw}]" if edition_kw else ""))
            img = best.get("image") or {}
            cover_url = img.get("super_url") or img.get("medium_url") or ""
            desc = _strip_html(best.get("description") or "") or (best.get("deck") or "").strip()
            if desc and len(desc) > 20:
                return (_truncate(desc), cover_url)
            return ("", cover_url)

        # ---- SINGLE ISSUE ----
        # Step 1: find the volume (cached per series name so a batch issue-fetch doesn't
        # re-search the volume for every issue — halves Comic Vine requests)
        cache_key = series.strip().lower()
        if cache_key in _VOL_CACHE:
            vol_id, vol_name = _VOL_CACHE[cache_key]
        else:
            vol_url = (
                f"{CV_BASE}/search/?api_key={key}&format=json"
                f"&query={urllib.parse.quote(series)}&resources=volume"
                f"&field_list=id,name,publisher&limit=10"
            )
            volumes = _fetch_json(vol_url).get("results", [])
            if not volumes:
                _log(f"no volume found for '{series}'", "warn")
                return ("", "")
            best_vol = max(volumes, key=lambda v: _word_overlap(series, v.get("name", "")))
            vol_id = best_vol.get("id")
            vol_name = best_vol.get("name", "?")
            _VOL_CACHE[cache_key] = (vol_id, vol_name)
            _log(f"volume match: '{vol_name}' (id={vol_id})")

        # Step 2: fetch the exact issue
        issue_url = (
            f"{CV_BASE}/issues/?api_key={key}&format=json"
            f"&filter=volume:{vol_id},issue_number:{issue_num}"
            f"&field_list=name,deck,description,issue_number,image&limit=5"
        )
        issues = _fetch_json(issue_url).get("results", [])
        if not issues:
            _log(f"no issue #{issue_num} in '{vol_name}'", "warn")
            return ("", "")

        # Skip TPB/collection rows, take the first real issue
        issue = None
        for cand in issues:
            deck = (cand.get("deck") or "").lower()
            if not any(deck.startswith(m) for m in COLLECTION_MARKERS):
                issue = cand
                break
        if issue is None:
            issue = issues[0]
        _log(f"issue match: '{vol_name}' #{issue.get('issue_number')}")

        # Step 3: cover URL
        img = issue.get("image") or {}
        cover_url = img.get("super_url") or img.get("medium_url") or ""

        # Step 4: synopsis
        desc = _strip_html(issue.get("description") or "")
        if desc and len(desc) > 20:
            return (_truncate(desc), cover_url)
        deck = (issue.get("deck") or "").strip()
        if deck and len(deck) > 20:
            return (_truncate(deck), cover_url)
        return ("", cover_url)

    except Exception as e:
        _log(f"synopsis/cover fetch failed: {e}", "warn")
    return ("", "")


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------

def download_cover_from_url(
    cover_url: str,
    series: str,
    issue_num: str,
    covers_dir: str | Path,
) -> str | None:
    """
    Download a cover image URL to covers_dir with a normalized filename.
    Filename format: '<safe series>-<issue_num><ext>' (e.g. 'Uncanny X-Men-202.jpg')
    so find_local_cover() will match it on the next run. Skips if it exists.
    """
    if not cover_url or not series or not issue_num:
        return None

    covers_dir = Path(covers_dir)

    ext = ".jpg"
    url_lower = cover_url.lower().split("?")[0]
    for cand in (".png", ".jpg", ".jpeg", ".webp"):
        if url_lower.endswith(cand):
            ext = cand
            break

    safe_series = re.sub(r"[^\w\s-]", "", series).strip()
    dest = covers_dir / f"{safe_series}-{issue_num}{ext}"
    if dest.exists():
        _log(f"cover already exists: {dest.name}")
        return str(dest)

    try:
        covers_dir.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(cover_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            dest.write_bytes(resp.read())
        _log(f"cover downloaded: {dest.name}", "ok")
        return str(dest)
    except Exception as e:
        _log(f"cover download failed: {e}", "warn")
        return None


# --------------------------------------------------------------------------
# One-call convenience wrapper
# --------------------------------------------------------------------------

def get_cover(
    series: str,
    issue_num: str,
    covers_dir: str | Path = "covers",
    api_key: str | None = None,
) -> str | None:
    """
    The 'just give me a cover' entry point.
      1. Return a matching local file if one already exists (no network).
      2. Otherwise fetch the Comic Vine cover URL and download it.
    Returns the cover file path, or None if everything fails.
    """
    local = find_local_cover(series, issue_num, covers_dir)
    if local:
        _log(f"using local cover: {Path(local).name}")
        return local

    _synopsis, cover_url = fetch_comic_synopsis(
        series=series, issue_num=issue_num, api_key=api_key
    )
    if cover_url:
        return download_cover_from_url(cover_url, series, issue_num, covers_dir)

    _log("Comic Vine returned no cover image", "warn")
    return None


# --------------------------------------------------------------------------
# CLI / smoke test:  python comic_cover_fetch.py "Uncanny X-Men" 202 ./covers
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3:
        s, n = sys.argv[1], sys.argv[2]
        d = sys.argv[3] if len(sys.argv) > 3 else "covers"
        print("RESULT:", get_cover(s, n, d))
    else:
        # Offline self-test of the matching logic (no network).
        assert extract_issue_key("Uncanny X-Men-202.png") == "uncannyxmen202"
        assert extract_issue_key("Avengers 289") == "avengers289"
        assert extract_issue_key("Amazing-Spider-Man-394.jpg") == "amazingspiderman394"
        print("Self-test OK. Usage: python comic_cover_fetch.py \"<series>\" <issue> [covers_dir]")
