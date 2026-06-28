#!/usr/bin/env python3
"""
serve.py — one command that runs BOTH the viewer and the editor, and lets
the editor save changes back to data/books.json.

Why this exists: browsers can't write files on their own, so the editor
page POSTs changes here and this server writes them to disk. It also serves
the static files, so you only run ONE thing.

USAGE
    python serve.py
then open:
    http://localhost:8000/viewer.html       (the OBS slide)
    http://localhost:8000/editor.html        (fix ranges / covers / notes)

Stop it with Ctrl+C in the terminal.
"""
import json, os, re, sys, subprocess, http.server, socketserver, urllib.parse, urllib.request, shutil, datetime

PORT = int(os.environ.get("PORT", "8000"))       # honors $PORT (preview/hosting); defaults to 8000
DATA = os.path.join("data", "books.json")        # default save target (single-series / legacy)
ROOT = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    # ---- helpers ------------------------------------------------------
    def _send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self, limit=20 * 1024 * 1024):
        length = int(self.headers.get("Content-Length", 0))
        if length > limit:          # cap: don't read an unbounded body into memory
            return None
        return self.rfile.read(length)

    def _query(self, name, default=None):
        q = urllib.parse.urlparse(self.path)
        return (urllib.parse.parse_qs(q.query).get(name) or [default])[0]

    def _manifest(self):
        man = os.path.join(ROOT, "data", "series.json")
        try:
            with open(man, encoding="utf-8") as f:
                return json.load(f), man
        except Exception:
            return None, man

    def _series_entry(self, series):
        manifest, _ = self._manifest()
        if manifest is None:
            return None
        return next((e for e in manifest if e.get("id") == series), None)

    def _series_file(self, series):
        """Resolve a series id to an absolute data path via the manifest whitelist.
        Defaults to data/books.json. None if unknown or it escapes data/ (no traversal)."""
        if not series:
            return os.path.join(ROOT, DATA)
        entry = self._series_entry(series)
        if not entry:
            return None
        fname = entry.get("file", "")
        if not re.match(r"^[A-Za-z0-9._-]+$", fname):      # safe filename only — never the raw id
            return None
        data_root = os.path.realpath(os.path.join(ROOT, "data"))
        target = os.path.realpath(os.path.join(data_root, fname))
        if os.path.commonpath([target, data_root]) != data_root:
            return None
        return target

    def _backup(self, path):
        if os.path.exists(path):
            bk = os.path.join(ROOT, "data", "backups")
            os.makedirs(bk, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            stem = os.path.splitext(os.path.basename(path))[0]
            shutil.copy(path, os.path.join(bk, f"{stem}-{stamp}.json"))

    def _atomic_write_json(self, path, obj):
        # write a temp file then replace — a failed write can never truncate the live
        # file; newline="\n" keeps LF on Windows so saves don't churn git diffs
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    # ---- GET: static files + web research -----------------------------
    def do_GET(self):
        if urllib.parse.urlparse(self.path).path == "/api/research":
            return self._do_research()
        return super().do_GET()

    def _do_research(self):
        """Server-side trivia lookup. Accepts only structured params (never a URL) and
        queries a fixed provider (Comic Vine) so the browser can't drive arbitrary
        outbound requests (no SSRF). Returns plain text the editor inserts via textContent."""
        coll = f"{self._query('series','')}: {self._query('title','')}".strip().strip(":").strip()
        if not coll:
            self._send_json(400, {"error": "series/title required"}); return
        try:
            scripts = os.path.join(ROOT, "scripts")
            if scripts not in sys.path:
                sys.path.insert(0, scripts)
            from comic_cover_fetch import fetch_comic_synopsis
        except Exception as e:
            self._send_json(500, {"error": f"research module unavailable: {e}"}); return
        try:
            summary, _cover = fetch_comic_synopsis(collection=coll, edition=self._query("format", ""))
        except Exception as e:
            self._send_json(502, {"error": f"lookup failed: {e}"}); return
        frm, to = self._query("from", ""), self._query("to", "")
        # Authoritative verification links (the user/Claude clicks through to confirm the
        # exact edition). We return URLs, not scraped content — robust and no SSRF.
        title, isbn, fmt = self._query("title", ""), self._query("isbn", ""), self._query("format", "")
        qte = urllib.parse.quote_plus((title + " " + fmt).strip())
        sources = []
        if isbn:
            sources.append({"name": "Penguin Random House",
                            "url": f"https://www.penguinrandomhouse.com/search/site?q={urllib.parse.quote_plus(isbn)}"})
        sources += [
            {"name": "Marvel Database (Epic/Omnibus wiki)",
             "url": f"https://marvel.fandom.com/wiki/Special:Search?query={qte}"},
            {"name": "Wikipedia",
             "url": f"https://en.wikipedia.org/w/index.php?search={qte}"},
            {"name": "Marvel.com",
             "url": f"https://www.marvel.com/search?query={urllib.parse.quote_plus(title)}"},
        ]
        self._send_json(200, {"summary": summary or "", "source": "Comic Vine",
                              "query": coll, "range": (f"#{frm}-#{to}" if frm and to else ""),
                              "sources": sources})

    # ---- POST: save / theme / rebuild ---------------------------------
    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path
        if route == "/save":    return self._do_save()
        if route == "/api/theme":   return self._do_theme()
        if route == "/api/rebuild": return self._do_rebuild()
        if route == "/api/cover":   return self._do_cover()
        if route == "/api/refetch-issue": return self._do_refetch_issue()
        if route == "/api/delete-issue":  return self._do_delete_issue()
        if route == "/api/new-series":    return self._do_new_series()
        self.send_error(404)

    def _do_save(self):
        raw = self._read_body()
        if raw is None:
            self.send_error(413, "payload too large"); return
        try:
            payload = json.loads(raw)
        except Exception as e:
            self.send_error(400, f"bad json: {e}"); return
        if not isinstance(payload, dict) or not isinstance(payload.get("books"), list):
            self.send_error(400, "payload must be an object with a 'books' array"); return
        path = self._series_file(self._query("series"))
        if path is None:
            self.send_error(400, "unknown or invalid series"); return
        self._backup(path)
        self._atomic_write_json(path, payload)
        self._send_json(200, {"ok": True})

    def _do_theme(self):
        raw = self._read_body(1024 * 1024)
        if raw is None:
            self.send_error(413, "payload too large"); return
        try:
            theme = json.loads(raw)
        except Exception as e:
            self.send_error(400, f"bad json: {e}"); return
        if not isinstance(theme, dict):
            self.send_error(400, "theme must be an object"); return
        series = self._query("series")
        manifest, man_path = self._manifest()
        if manifest is None:
            self.send_error(500, "no manifest"); return
        # find the entry IN this manifest object (not a fresh load) so the mutation
        # is what we write back
        entry = next((e for e in manifest if e.get("id") == series), None)
        if entry is None:
            self.send_error(400, "unknown series"); return
        self._backup(man_path)
        entry["theme"] = theme
        self._atomic_write_json(man_path, manifest)
        self._send_json(200, {"ok": True, "theme": theme})

    def _do_rebuild(self):
        """One-click CSV re-import: re-run build_books.py with the params stored in the
        manifest for this series (no flags for the user to remember). Enrichment + order
        survive (build_books preserves them)."""
        entry = self._series_entry(self._query("series"))
        if entry is None:
            self.send_error(400, "unknown series"); return
        if not entry.get("csv") or not entry.get("series_group"):
            # a hand-built series has no CLZ source — re-importing would overwrite it with nothing
            self.send_error(400, "this series wasn't imported from CLZ — nothing to re-import"); return
        csv_name = entry.get("csv", "export_comics.csv")
        if not re.match(r"^[A-Za-z0-9._ -]+$", csv_name) or not re.match(r"^[A-Za-z0-9._-]+$", entry.get("file", "")):
            self.send_error(400, "bad csv/file name"); return
        cmd = [sys.executable, os.path.join(ROOT, "scripts", "build_books.py"),
               "--csv", os.path.join(ROOT, csv_name),
               "--series-group", entry.get("series_group", ""),
               "--box", entry.get("box", ""),
               "--series-label", entry.get("label", entry["id"]),
               "--run-max", str(entry.get("run_max", 1000)),
               "--series-id", entry["id"],
               "--out", os.path.join(ROOT, "data", entry["file"])]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=120)
        except Exception as e:
            self._send_json(500, {"error": f"rebuild failed: {e}"}); return
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        self._send_json(200 if r.returncode == 0 else 500,
                        {"ok": r.returncode == 0, "output": out})

    def _do_cover(self):
        """Save an image the editor picked into covers/<name>.<ext> (by convention name=ISBN),
        so the user can attach a cover by file instead of typing a path. Browsers can't write
        files, so the bytes are POSTed here. The image is only ever served back as a static
        file, never executed; name/ext are validated and the path is confined to covers/."""
        name = self._query("name", "") or ""
        ext = (self._query("ext", "jpg") or "jpg").lower().lstrip(".")
        if not re.match(r"^[A-Za-z0-9._-]+$", name) or ".." in name:
            self.send_error(400, "bad cover name"); return
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            self.send_error(400, "unsupported image type"); return
        raw = self._read_body(20 * 1024 * 1024)
        if raw is None:
            self.send_error(413, "image too large"); return
        if len(raw) < 64:
            self.send_error(400, "empty/too-small image"); return
        covers_root = os.path.realpath(os.path.join(ROOT, "covers"))
        os.makedirs(covers_root, exist_ok=True)
        target = os.path.realpath(os.path.join(covers_root, f"{name}.{ext}"))
        if os.path.commonpath([target, covers_root]) != covers_root:   # never escape covers/
            self.send_error(400, "invalid path"); return
        tmp = target + ".tmp"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, target)
        rel = os.path.relpath(target, ROOT).replace("\\", "/")
        self._send_json(200, {"ok": True, "path": rel})

    def _issue_n(self):
        """Parse & bound the ?n=<legacy issue> param. Returns int or None."""
        try:
            n = int(self._query("n", ""))
        except (TypeError, ValueError):
            return None
        return n if 1 <= n <= 100000 else None

    def _do_refetch_issue(self):
        """Re-download ONE issue cover for a book's deep-dive wall (backs the editor's
        'redownload' button for a wrong/missing cover). Resolves via the same pinned-volume
        logic the batch fetcher uses, then writes covers/issues/<series>/<n>.jpg."""
        series = self._query("series")
        if not re.match(r"^[A-Za-z0-9._-]+$", series or ""):
            self.send_error(400, "bad series id"); return
        entry = self._series_entry(series)
        if entry is None:
            self.send_error(400, "unknown series"); return
        n = self._issue_n()
        if n is None:
            self.send_error(400, "bad issue number"); return
        try:
            scripts = os.path.join(ROOT, "scripts")
            if scripts not in sys.path:
                sys.path.insert(0, scripts)
            import fetch_issue_covers as fic
            from comic_cover_fetch import USER_AGENT
        except Exception as e:
            self._send_json(500, {"error": f"fetch module unavailable: {e}"}); return
        # an args-like object for cover_url_for: mapped series (asm/ff) ignore .series and use
        # the pinned LEGACY_MAPS volume; others fall back to the manifest's CV name/alt
        class _A: pass
        a = _A(); a.id = series
        a.series = entry.get("cv_series") or entry.get("label") or series
        a.alt_series = entry.get("cv_alt")
        try:
            url = fic.cover_url_for(n, a)
        except Exception as e:
            self._send_json(502, {"error": f"lookup failed: {e}"}); return
        if not url:
            self._send_json(404, {"error": f"no cover found for #{n}"}); return
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
        except Exception as e:
            self._send_json(502, {"error": f"download failed: {e}"}); return
        if len(data) < 1500:
            self._send_json(502, {"error": "image too small / not found"}); return
        out_dir = os.path.join(ROOT, "covers", "issues", series)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{n}.jpg")
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        self._send_json(200, {"ok": True, "path": rel, "bytes": len(data)})

    def _do_new_series(self):
        """Create a new series from the editor: either an empty shelf (add books by hand) or
        a CLZ CSV import (runs build_books.py, which writes the data file + manifest entry)."""
        raw = self._read_body(256 * 1024)
        if raw is None:
            self.send_error(413, "payload too large"); return
        try:
            p = json.loads(raw)
        except Exception as e:
            self.send_error(400, f"bad json: {e}"); return
        sid = (p.get("id") or "").strip()
        label = (p.get("label") or "").strip()
        mode = (p.get("mode") or "empty").strip()
        try:
            run_max = int(p.get("run_max") or 1000)
        except (TypeError, ValueError):
            self.send_error(400, "bad run_max"); return
        if not re.match(r"^[a-z0-9][a-z0-9_-]{0,38}$", sid):    # safe, permanent filename stem
            self.send_error(400, "id must be lowercase letters/numbers/-/_ and start alphanumeric"); return
        if not label:
            self.send_error(400, "label required"); return
        manifest, man_path = self._manifest()
        if manifest is None:
            manifest = []
        if any(e.get("id") == sid for e in manifest):
            self.send_error(409, f"series id '{sid}' already exists"); return
        data_dir = os.path.join(ROOT, "data")
        os.makedirs(data_dir, exist_ok=True)
        out_path = os.path.join(data_dir, f"{sid}.json")

        if mode == "clz":
            csv_name = (p.get("csv") or "").strip()
            group = (p.get("series_group") or "").strip()
            box = (p.get("box") or "").strip()
            if not re.match(r"^[A-Za-z0-9._ -]+$", csv_name) or not group or not box:
                self.send_error(400, "csv/series_group/box required for a CLZ import"); return
            if not os.path.exists(os.path.join(ROOT, csv_name)):
                self.send_error(400, f"csv not found: {csv_name}"); return
            cmd = [sys.executable, os.path.join(ROOT, "scripts", "build_books.py"),
                   "--csv", os.path.join(ROOT, csv_name),
                   "--series-group", group, "--box", box,
                   "--series-label", label, "--run-max", str(run_max),
                   "--series-id", sid, "--out", out_path]    # build_books upserts the manifest itself
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=120)
            except Exception as e:
                self._send_json(500, {"error": f"import failed: {e}"}); return
            out = ((r.stdout or "") + (r.stderr or "")).strip()
            if r.returncode != 0:
                self._send_json(500, {"ok": False, "error": out or "build_books failed"}); return
            self._send_json(200, {"ok": True, "id": sid, "output": out}); return

        # empty series — write a stub data file and a minimal manifest entry
        self._atomic_write_json(out_path, {"series": label, "run_max": run_max, "count": 0, "books": []})
        manifest.append({"id": sid, "label": label, "file": f"{sid}.json", "run_max": run_max, "theme": {}})
        self._backup(man_path)
        self._atomic_write_json(man_path, manifest)
        self._send_json(200, {"ok": True, "id": sid})

    def _do_delete_issue(self):
        """Delete ONE issue cover (the editor's 'remove' button for a wrong cover). Path is
        confined to covers/issues/ so a crafted series/n can't escape."""
        series = self._query("series")
        if not re.match(r"^[A-Za-z0-9._-]+$", series or ""):
            self.send_error(400, "bad series id"); return
        if self._series_entry(series) is None:
            self.send_error(400, "unknown series"); return
        n = self._issue_n()
        if n is None:
            self.send_error(400, "bad issue number"); return
        issues_root = os.path.realpath(os.path.join(ROOT, "covers", "issues"))
        target = os.path.realpath(os.path.join(issues_root, series, f"{n}.jpg"))
        if os.path.commonpath([target, issues_root]) != issues_root:
            self.send_error(400, "invalid path"); return
        existed = os.path.exists(target)
        if existed:
            os.remove(target)
        self._send_json(200, {"ok": True, "deleted": existed})

    def end_headers(self):
        # let the editor fetch/post without cache headaches
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

if __name__ == "__main__":
    os.chdir(ROOT)
    # loopback only — do not expose the project + unauthenticated /save writer to the LAN.
    # Threading so a slow request (e.g. /api/research's outbound call) can't block the
    # viewer/editor from loading on a single-threaded server.
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"\n  BCE Legacy tool running.")
        print(f"  Slide  :  http://localhost:{PORT}/viewer.html")
        print(f"  Editor :  http://localhost:{PORT}/editor.html")
        print(f"\n  (every save backs up to data/backups/ first)")
        print(f"  Ctrl+C to stop.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped.")
