"""Capture portfolio screenshots of the fully-seeded Flutter web build.

Drives the `main_portfolio` build (signed-in session + in-memory demo data for
every repository) with the pre-installed Chromium at a phone viewport, visiting
each feature route by hash and tapping through the couple of overlays that have
no route of their own. Writes light + dark PNGs to portfolio/images/.
"""
from __future__ import annotations

import functools
import http.server
import socketserver
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "build" / "web"
OUT = ROOT.parent / "portfolio" / "images"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
VIEWPORT = {"width": 390, "height": 844}

# name, hash-route, [taps as (x,y)] performed after the route settles.
SHOTS = [
    ("feed", "/feed", []),
    ("feed-sort", "/feed", [(314, 28)]),           # open the Sort menu
    ("feed-add-url", "/feed", [(356, 28)]),        # open the Add-a-job dialog (Link)
    ("feed-add-text", "/feed", [(356, 28), (250, 331)]),  # switch to Paste text
    ("job-detail", "/feed/job/j1", []),
    ("saved", "/saved", []),
    ("applications", "/applications", []),
    ("insights", "/applications/insights", []),
    ("draft-detail", "/applications/draft/d1", []),
    ("profile", "/profile", []),
    ("profile-edit", "/profile/edit", []),
    ("boards", "/profile/boards", []),
    ("notifications", "/profile/notifications", []),
    ("usage", "/profile/usage", []),
    ("llm-key", "/profile/key", []),
    ("appearance", "/profile/appearance", []),
    ("resume", "/profile/resume", []),
]

_CHROME_ARGS = [
    "--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
]


class _Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        super().end_headers()

    def log_message(self, *a):
        pass


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve() -> _Server:
    handler = functools.partial(_Handler, directory=str(WEB_DIR))
    httpd = _Server(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    httpd = serve()
    port = httpd.server_address[1]
    base = f"http://127.0.0.1:{port}/"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME, args=_CHROME_ARGS)
            for scheme in ("dark", "light"):
                ctx = browser.new_context(viewport=VIEWPORT, color_scheme=scheme)
                page = ctx.new_page()
                page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))
                for i, (name, route, taps) in enumerate(SHOTS):
                    # A unique query forces a full reload (not a hash-only change),
                    # so no overlay/dialog from a previous shot leaks into this one.
                    page.goto(f"{base}?s={i}#{route}")
                    page.wait_for_selector("flutter-view, flt-glass-pane, canvas",
                                           timeout=30000)
                    # Let the app boot + the route's data settle and animate in.
                    page.wait_for_timeout(3200)
                    for (x, y) in taps:
                        page.mouse.click(x, y)
                        page.wait_for_timeout(900)
                    page.screenshot(path=str(OUT / f"{name}-{scheme}.png"))
                    print(f"  captured {name}-{scheme}")
                ctx.close()
            browser.close()
    finally:
        httpd.shutdown()
    print(f"screenshots written to {OUT}")


if __name__ == "__main__":
    main()
