from http.server import BaseHTTPRequestHandler
from pathlib import Path

UPLOAD_DIR = Path('/srv/orders/uploads')

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/attachments':
            self.send_error(404); return
        target = UPLOAD_DIR / self.headers['X-Filename']
        target.write_bytes(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(201); self.end_headers()
