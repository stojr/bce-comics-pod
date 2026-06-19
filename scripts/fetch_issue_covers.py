#!/usr/bin/env python3
"""
fetch_issue_covers.py — download per-issue cover thumbnails for a legacy range,
so the viewer can show "the issues inside this book" as a contents strip.

Saves to covers/issues/<series-id>/<issue>.jpg. Standard library only; reuses the
single-issue Comic Vine lookup in comic_cover_fetch.py.

  python scripts/fetch_issue_covers.py --series "West Coast Avengers" --id wca \
      --from 38 --to 52 --alt-series "Avengers West Coast"
"""
import argparse, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comic_cover_fetch import fetch_comic_synopsis, USER_AGENT

def main():
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", required=True, help="Comic Vine series name, e.g. 'West Coast Avengers'")
    ap.add_argument("--id", required=True, help="series id (folder under covers/issues/)")
    ap.add_argument("--from", dest="f", type=int, required=True)
    ap.add_argument("--to", dest="t", type=int, required=True)
    ap.add_argument("--alt-series", default=None, help="fallback series name for a renumbered run")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    out_dir = os.path.join("covers", "issues", args.id)
    os.makedirs(out_dir, exist_ok=True)
    got = skip = miss = 0
    for n in range(args.f, args.t + 1):
        path = os.path.join(out_dir, f"{n}.jpg")
        if os.path.exists(path) and not args.force:
            skip += 1; continue
        _, url = fetch_comic_synopsis(series=args.series, issue_num=str(n))
        if not url and args.alt_series:
            _, url = fetch_comic_synopsis(series=args.alt_series, issue_num=str(n))
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
        time.sleep(0.4)
    print(f"\nIssue covers [{args.id} #{args.f}-{args.t}]: {got} downloaded, {skip} present, {miss} missing")

if __name__ == "__main__":
    main()
