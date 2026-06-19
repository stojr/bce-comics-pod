#!/usr/bin/env python3
"""
enrich_legacy.py — fill in the legacy issue ranges + gaps for each book.

This is the one step that can't be fully automated from your CSV, because
the legacy issue range a collected edition covers isn't in the export. It
has to come from an external source (Marvel's collection listings, comic
databases, or the book's indicia).

THREE WAYS TO USE IT
  1. REVIEW MODE (default): prints every book and its current range so you
     can eyeball what's done and what's missing.
       python scripts/enrich_legacy.py

  2. SET MODE: write a range for one book by ISBN.
       python scripts/enrich_legacy.py --isbn 9780785188346 --from 1 --to 17 --verified
       python scripts/enrich_legacy.py --isbn 9780785188346 --gap 18 30
       python scripts/enrich_legacy.py --isbn 9780785188346 --pod "First Sinister Six · Ditko"
       python scripts/enrich_legacy.py --isbn 9780785188346 --also "Omnibus Vol. 1"

  3. CLAUDE CODE MODE (recommended): open this folder in Claude Code and ask
     it to "look up the legacy issue range for each unverified book in
     books.json and set it." Claude can web-search each ISBN/title, find the
     issues collected, and call this script (or edit books.json directly).
     The 'verified' flag lets you trust ranges you've confirmed vs. seeds.

Everything writes back to data/books.json. build_books.py preserves these
fields on rebuild (matched by ISBN), so you only do the lookup once.
"""
import argparse, json, sys

DATA = "data/books.json"

def load(): return json.load(open(DATA, encoding="utf-8"))
def save(d): json.dump(d, open(DATA,"w",encoding="utf-8"), indent=2, ensure_ascii=False)

def review(d):
    done=0
    print(f"\n{d['series']} — {d['count']} books\n" + "="*62)
    for i,b in enumerate(d["books"],1):
        if b["legacy_from"] is not None:
            rng=f"#{b['legacy_from']}–{b['legacy_to']}"
            flag="✓" if b["verified"] else "≈"
            done+=1
        else:
            rng="— needs lookup —"; flag=" "
        print(f"{i:2}. {flag} {rng:16} [{b['format'][:16]:16}] {b['title'][:34]}")
    print("="*62)
    print(f"{done}/{d['count']} have ranges · "
          f"{sum(1 for b in d['books'] if b['verified'])} verified · "
          f"{d['count']-done} still need lookup")
    print("\nTip: open this folder in Claude Code and ask it to look up the")
    print("unverified ranges by ISBN/title, then re-run with --verified.\n")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--isbn")
    ap.add_argument("--from", dest="f", type=int)
    ap.add_argument("--to", dest="t", type=int)
    ap.add_argument("--gap", nargs=2, type=int, metavar=("FROM","TO"))
    ap.add_argument("--pod")
    ap.add_argument("--also")
    ap.add_argument("--verified", action="store_true")
    args=ap.parse_args()

    d=load()
    if not args.isbn:
        review(d); return

    b=next((x for x in d["books"] if x["isbn"]==args.isbn), None)
    if not b:
        print(f"No book with ISBN {args.isbn}"); sys.exit(1)
    if args.f is not None: b["legacy_from"]=args.f
    if args.t is not None: b["legacy_to"]=args.t
    if args.gap: b.setdefault("gaps_avail",[]).append(list(args.gap))
    if args.pod is not None: b["pod"]=args.pod
    if args.also is not None: b["also_in"]=args.also
    if args.verified: b["verified"]=True
    save(d)
    print(f"Updated {b['title']}: "
          f"#{b['legacy_from']}–{b['legacy_to']} "
          f"{'(verified)' if b['verified'] else '(unverified)'}")

if __name__=="__main__":
    main()
