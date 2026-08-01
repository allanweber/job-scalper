"""Capture mobile-viewport screenshots of M4 (job detail + saved tab).

Builds the web app with `lib/main_m4_shots.dart` and drives the pre-installed
Chromium at a phone viewport via `?screen=` / `?state=`, light + dark.
Mirrors tool/feed_shots.py.
"""
from __future__ import annotations

import functools
import http.server
import socketserver
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "build" / "web"
OUT = ROOT / "screenshots" / "m4"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
VIEWPORT = {"width": 390, "height": 844}

# (name, query)
SHOTS = [
    ("detail", "screen=detail&state=ready"),
    ("saved", "screen=saved&state=ready"),
    ("saved-empty", "screen=saved&state=empty"),
]


class _Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        super().end_headers()

    def log_message(self, *args):
        pass


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve() -> tuple[_Server, int]:
    handler = functools.partial(_Handler, directory=str(WEB_DIR))
    httpd = _Server(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


_CHROME_ARGS = [
    "--no-sandbox",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    httpd, port = serve()
    base = f"http://127.0.0.1:{port}/"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME, args=_CHROME_ARGS)
            for scheme in ("light", "dark"):
                ctx = browser.new_context(viewport=VIEWPORT, color_scheme=scheme)
                page = ctx.new_page()
                for name, query in SHOTS:
                    page.goto(f"{base}?{query}", wait_until="load")
                    time.sleep(3.0)
                    out = OUT / f"{name}-{scheme}.png"
                    page.screenshot(path=str(out))
                    print(f"wrote {out.relative_to(ROOT)}")
                ctx.close()
            browser.close()
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main()
