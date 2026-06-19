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
import json, os, http.server, socketserver, urllib.parse, shutil, datetime

PORT = 8000
DATA = os.path.join("data", "books.json")
ROOT = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def do_POST(self):
        if self.path != "/save":
            self.send_error(404); return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except Exception as e:
            self.send_error(400, f"bad json: {e}"); return

        path = os.path.join(ROOT, DATA)
        # timestamped backup before every write — never lose data
        if os.path.exists(path):
            bk = os.path.join(ROOT, "data", "backups")
            os.makedirs(bk, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy(path, os.path.join(bk, f"books-{stamp}.json"))

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

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
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"\n  BCE Legacy tool running.")
        print(f"  Slide  :  http://localhost:{PORT}/viewer.html")
        print(f"  Editor :  http://localhost:{PORT}/editor.html")
        print(f"\n  (every save backs up to data/backups/ first)")
        print(f"  Ctrl+C to stop.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped.")
