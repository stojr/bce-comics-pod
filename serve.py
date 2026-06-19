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
import json, os, re, http.server, socketserver, urllib.parse, shutil, datetime

PORT = 8000
DATA = os.path.join("data", "books.json")        # default save target (single-series / legacy)
ROOT = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def _resolve_target(self):
        """Absolute path to write for this POST, from ?series=<id> looked up in the
        data/series.json manifest (a whitelist). Defaults to data/books.json. Returns
        None if the series id is unknown or resolves outside data/ (no path traversal)."""
        q = urllib.parse.urlparse(self.path)
        series = (urllib.parse.parse_qs(q.query).get("series") or [None])[0]
        if not series:
            return os.path.join(ROOT, DATA)
        man = os.path.join(ROOT, "data", "series.json")
        try:
            with open(man, encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            return None
        entry = next((e for e in manifest if e.get("id") == series), None)
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

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/save":
            self.send_error(404); return
        length = int(self.headers.get("Content-Length", 0))
        if length > 20 * 1024 * 1024:          # cap: don't read an unbounded body into memory
            self.send_error(413, "payload too large"); return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except Exception as e:
            self.send_error(400, f"bad json: {e}"); return

        # shape check — never let a malformed blob clobber the live file
        if not isinstance(payload, dict) or not isinstance(payload.get("books"), list):
            self.send_error(400, "payload must be an object with a 'books' array"); return

        path = self._resolve_target()
        if path is None:
            self.send_error(400, "unknown or invalid series"); return
        stem = os.path.splitext(os.path.basename(path))[0]
        # timestamped backup before every write — never lose data
        if os.path.exists(path):
            bk = os.path.join(ROOT, "data", "backups")
            os.makedirs(bk, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy(path, os.path.join(bk, f"{stem}-{stamp}.json"))

        # atomic write: write a temp file in the same dir, then replace — a failed
        # or interrupted write can never truncate the live books.json
        tmp = path + ".tmp"
        # newline="\n" keeps LF on Windows (text mode would translate to CRLF and
        # churn every line on each save, polluting git diffs)
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def end_headers(self):
        # let the editor fetch/post without cache headaches
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

if __name__ == "__main__":
    os.chdir(ROOT)
    # loopback only — do not expose the project + unauthenticated /save writer to the LAN
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"\n  BCE Legacy tool running.")
        print(f"  Slide  :  http://localhost:{PORT}/viewer.html")
        print(f"  Editor :  http://localhost:{PORT}/editor.html")
        print(f"\n  (every save backs up to data/backups/ first)")
        print(f"  Ctrl+C to stop.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped.")
