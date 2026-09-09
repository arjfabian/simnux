"""SPA-aware development server for the SIMNUX frontend.

Serves static files from the frontend directory and falls back to
``index.html`` for any path that does not correspond to an existing file,
enabling scenario deep-linking (e.g. ``/shadow_key``) to work without a
separate router.
"""

import http.server
from pathlib import Path
import sys


PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
DIRECTORY = Path(__file__).resolve().parent


class SPAHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Extends ``SimpleHTTPRequestHandler`` with SPA fallback routing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        clean_path = self.path.split("?")[0]
        translated = self.translate_path(clean_path)
        if not Path(translated).is_file():
            self.path = "/index.html"
        super().do_GET()


if __name__ == "__main__":
    server = http.server.HTTPServer(("", PORT), SPAHTTPRequestHandler)
    sys.stderr.write(f"Serving SIMNUX frontend at http://localhost:{PORT}\n")
    server.serve_forever()
