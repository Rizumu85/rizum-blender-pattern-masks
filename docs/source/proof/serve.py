"""Serves this folder for the proof shots and saves each one (POST /save) into
./out (not in the repo). python serve.py, then open http://127.0.0.1:8779/."""
import http.server, os, sys, urllib.parse
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "out")
os.makedirs(OUT, exist_ok=True)
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=ROOT, **k)
    def do_POST(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        name = os.path.basename(q["name"][0])
        data = self.rfile.read(int(self.headers["Content-Length"]))
        open(os.path.join(OUT, name + ".png"), "wb").write(data)
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
http.server.ThreadingHTTPServer(("127.0.0.1", 8779), H).serve_forever()
