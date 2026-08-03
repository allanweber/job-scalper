"""Capture mobile-viewport screenshots of the Flutter web build.

No Android emulator in this environment, so we build the app for web and drive
it with the pre-installed Chromium at a phone viewport. Uses the `main_demo`
build (pre-seeded signed-in session) so the nav shell renders without a backend.
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
OUT = ROOT / "screenshots"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
PORT = 0
VIEWPORT = {"width": 390, "height": 844}


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Static server that sets cross-origin isolation (needed by the web engine)."""

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


def serve() -> _Server:
    handler = functools.partial(_Handler, directory=str(WEB_DIR))
    httpd = _Server(("127.0.0.1", PORT), handler)
    globals()["PORT"] = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


_CHROME_ARGS = [
    "--no-sandbox",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    httpd = serve()
    url = f"http://127.0.0.1:{PORT}/"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME, args=_CHROME_ARGS)
            for scheme in ("light", "dark"):
                ctx = browser.new_context(viewport=VIEWPORT, color_scheme=scheme)
                page = ctx.new_page()
                page.on("console", lambda m: print(f"  [console.{m.type}] {m.text}"))
                page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))

                # Launch splash (only need it once; capture in light).
                page.goto(url)
                page.wait_for_selector("flutter-view, flt-glass-pane, canvas",
                                       timeout=30000)
                if scheme == "light":
                    page.wait_for_timeout(900)
                    page.screenshot(path=str(OUT / "01-launch.png"))

                # Splash routes to the shell (~1.6s) — land on Feed.
                page.wait_for_timeout(2600)
                page.screenshot(path=str(OUT / f"02-feed-{scheme}.png"))

                # Walk the four tabs by tapping the nav bar (icons, left→right).
                for idx, name in enumerate(["feed", "saved", "applications", "profile"]):
                    # NavigationBar destinations are evenly spaced; tap by fraction.
                    x = VIEWPORT["width"] * (idx + 0.5) / 4
                    y = VIEWPORT["height"] - 30
                    page.mouse.click(x, y)
                    page.wait_for_timeout(500)
                    page.screenshot(path=str(OUT / f"0{3+idx}-{name}-{scheme}.png"))

                ctx.close()
            browser.close()
    finally:
        httpd.shutdown()
    print(f"screenshots written to {OUT}")


if __name__ == "__main__":
    main()
