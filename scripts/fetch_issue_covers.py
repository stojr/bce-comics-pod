#!/usr/bin/env python3
"""
fetch_issue_covers.py — download per-issue cover thumbnails so the viewer can show
"the issues inside this book" (and the issues in a small known gap) as a strip.

Saves to covers/issues/<series-id>/<issue>.jpg. Standard library only; reuses the
single-issue Comic Vine lookup in comic_cover_fetch.py.

TWO MODES
  1. Single range:
       python scripts/fetch_issue_covers.py --series "West Coast Avengers" --id wca \
           --from 38 --to 52 --alt-series "Avengers West Coast"

  2. Whole series from its data file (RECOMMENDED): fetches every owned book's issues,
     plus any available-gap (gaps_avail) issues, plus SMALL holes between consecutive
     owned volumes (<= --max-gap). Large/undefined gaps are skipped — we wouldn't know
     how to break them up.
       python scripts/fetch_issue_covers.py --series "West Coast Avengers" --id wca \
           --data data/wca.json --alt-series "Avengers West Coast"
"""
import argparse, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comic_cover_fetch import fetch_comic_synopsis, USER_AGENT

# Legacy issue number -> (printed number, Comic Vine series name, volume start year).
# Comic Vine indexes by the printed number within a SPECIFIC volume, not the legacy number,
# so modern issues (legacy != printed, and in a different volume) need this conversion.
# (legacy_lo, legacy_hi, cv_series, start_year, offset, cv_volume_id)  ->  printed = legacy - offset
# cv_volume_id PINS the Comic Vine volume so resolution can't drift to a same-named volume
# (e.g. FF Heroes Reborn 1996 vs FF vol 1 1961). IDs verified against the Comic Vine API.
LEGACY_MAPS = {
    "asm": [
        (1,   441, "Amazing Spider-Man", 1963, 0,   2127),    # vol 1 (1963)  #1-441
        (442, 499, "Amazing Spider-Man", 1999, 441, 78701),   # vol 2 (1999)  #1-58
        (500, 700, "Amazing Spider-Man", 1963, 0,   2127),    # vol 1 resumed legacy numbering #500-700
        (770, 775, "Amazing Spider-Man", 2015, 751, 85076),   # vol 4 (2015)  #19-24 (Clone Conspiracy)
        (876, 894, "Amazing Spider-Man", 2018, 801, 112161),  # vol 5 (2018)  #75-93 (Beyond)
    ],
    "ff": [
        (1,   416, "Fantastic Four", 1961, 0,   2045),    # vol 1 (1961)
        (417, 428, "Fantastic Four", 1996, 416, 9462),    # vol 2 Heroes Reborn (1996) #1-12
        (429, 498, "Fantastic Four", 1998, 428, 6211),    # vol 3 (1998) #1-70
        (500, 588, "Fantastic Four", 1998, 0,   6211),    # vol 3 resumed legacy numbering #500-588
        (600, 611, "Fantastic Four", 1998, 0,   6211),    # vol 3 #600-611
        (612, 627, "Fantastic Four", 2013, 611, 53921),   # Fraction (2013) #1-16
        (628, 645, "Fantastic Four", 2014, 627, 71949),   # Robinson (2014) #1-18
        (646, 693, "Fantastic Four", 2018, 645, 112685),  # Slott (2018) #1-48
        (694, 725, "Fantastic Four", 2023, 693, 145912),  # North (2023) #1-32
    ],
}

def map_legacy(series_id, n):
    """legacy number -> (printed_number, cv_series, start_year, cv_volume_id), or None."""
    for lo, hi, cv, yr, off, vol in LEGACY_MAPS.get(series_id, []):
        if lo <= n <= hi:
            return (n - off, cv, yr, vol)
    return None

def cover_url_for(n, args):
    """Resolve a cover URL for legacy issue n, via the legacy map if the series has one."""
    if args.id in LEGACY_MAPS:
        seg = map_legacy(args.id, n)
        if not seg:
            return ""                                   # outside known segments -> skip
        printed, cv, yr, vol = seg
        _, url = fetch_comic_synopsis(series=cv, issue_num=str(printed), start_year=yr, volume_id=vol)
        return url
    _, url = fetch_comic_synopsis(series=args.series, issue_num=str(n))
    if not url and args.alt_series:
        _, url = fetch_comic_synopsis(series=args.alt_series, issue_num=str(n))
    return url

def _runs(missing):
    """Group a sorted list of ints into contiguous (start, end) runs."""
    runs, run = [], []
    for x in missing:
        if run and x == run[-1] + 1:
            run.append(x)
        else:
            if run: runs.append((run[0], run[-1]))
            run = [x]
    if run: runs.append((run[0], run[-1]))
    return runs

def issues_for_data(data_path, max_gap):
    """Issues to fetch for a whole series: owned + available-gap + small holes between
    owned volumes. Returns (sorted_issue_list, human_readable_info)."""
    d = json.load(open(data_path, encoding="utf-8"))
    owned, avail = set(), set()
    for b in d.get("books", []):
        f, t = b.get("legacy_from"), b.get("legacy_to")
        if f is not None and t is not None and t >= f:
            owned.update(range(f, t + 1))
        for g in (b.get("gaps_avail") or []):
            if len(g) >= 2 and g[1] >= g[0]:
                avail.update(range(g[0], g[1] + 1))
    universe = owned | avail
    if not universe:
        return [], "no ranges set"
    lo, hi = min(universe), max(universe)
    missing = sorted(set(range(lo, hi + 1)) - universe)
    small, skipped = set(), []
    for a, z in _runs(missing):
        if z - a + 1 <= max_gap:
            small.update(range(a, z + 1))           # a single-volume-ish gap — include it
        else:
            skipped.append((a, z))                  # too big / undefined — leave it
    issues = sorted(owned | avail | small)
    info = f"{len(owned)} owned + {len(avail)} available-gap + {len(small)} small-gap issues"
    if skipped:
        info += "  |  SKIPPED large gaps: " + ", ".join(f"#{a}-{z}" for a, z in skipped)
    return issues, info

def main():
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # so it runs from any folder
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True, help="Comic Vine series name")
    ap.add_argument("--id", required=True, help="series id (folder under covers/issues/)")
    ap.add_argument("--from", dest="f", type=int)
    ap.add_argument("--to", dest="t", type=int)
    ap.add_argument("--data", help="series data file — fetch the whole shelf + small gaps")
    ap.add_argument("--max-gap", type=int, default=25, help="largest gap (issues) to fill")
    ap.add_argument("--alt-series", default=None, help="fallback series name for a renumbered run")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between issues (slower avoids Comic Vine burst throttling / HTTP 420)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.data:
        issues, info = issues_for_data(args.data, args.max_gap)
        print(f"[{args.id}] {info}\n")
    elif args.f is not None and args.t is not None:
        issues = list(range(args.f, args.t + 1))
    else:
        print("need either --data or --from/--to"); return

    out_dir = os.path.join("covers", "issues", args.id)
    os.makedirs(out_dir, exist_ok=True)
    got = skip = miss = 0
    for n in issues:
        path = os.path.join(out_dir, f"{n}.jpg")
        if os.path.exists(path) and not args.force:
            skip += 1; continue
        url = cover_url_for(n, args)
        if url:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read()
                if len(data) > 1500:
                    with open(path, "wb") as fh: fh.write(data)
                    print(f"  ✓ #{n}"); got += 1
                else:
                    print(f"  ✗ #{n} (tiny image)"); miss += 1
            except Exception as e:
                print(f"  ✗ #{n} ({e})"); miss += 1
        else:
            print(f"  ✗ #{n} (no cover found)"); miss += 1
        time.sleep(args.delay)
    print(f"\nIssue covers [{args.id}]: {got} downloaded, {skip} already present, {miss} missing")

if __name__ == "__main__":
    main()
