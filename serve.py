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
import json, os, re, sys, subprocess, http.server, socketserver, urllib.parse, shutil, datetime

PORT = 8000
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
            summary, _cover = fetch_comic_synopsis(collection=coll)
        except Exception as e:
            self._send_json(502, {"error": f"lookup failed: {e}"}); return
        frm, to = self._query("from", ""), self._query("to", "")
        self._send_json(200, {"summary": summary or "", "source": "Comic Vine",
                              "query": coll, "range": (f"#{frm}-#{to}" if frm and to else "")})

    # ---- POST: save / theme / rebuild ---------------------------------
    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path
        if route == "/save":    return self._do_save()
        if route == "/api/theme":   return self._do_theme()
        if route == "/api/rebuild": return self._do_rebuild()
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
