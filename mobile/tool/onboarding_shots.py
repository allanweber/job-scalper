"""Capture mobile-viewport screenshots of the onboarding flow.

Builds the web app with `lib/main_shots.dart` and drives the pre-installed
Chromium at a phone viewport, loading each onboarding step via the `?step=`
query param in both light and dark. See `screenshots.py` for the shell/feed
version; this shares the same server + Chromium setup.
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
OUT = ROOT / "screenshots" / "onboarding"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
VIEWPORT = {"width": 390, "height": 844}

# (order, step-name) — matches OnboardingStep.name values.
STEPS = [
    "welcome",
    "signIn",
    "consent",
    "resume",
    "buildingProfile",
    "reviewProfile",
    "boards",
    "notifications",
    "buildingFeed",
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
                page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))
                for i, step in enumerate(STEPS):
                    page.goto(f"{base}?step={step}")
                    page.wait_for_selector("flutter-view, flt-glass-pane, canvas",
                                           timeout=30000)
                    # Let fonts + the first frame settle (async steps animate in).
                    page.wait_for_timeout(1500)
                    out = OUT / f"{i:02d}-{step}-{scheme}.png"
                    page.screenshot(path=str(out))
                    print(f"  wrote {out.name}")
                ctx.close()
            browser.close()
    finally:
        httpd.shutdown()
    print(f"onboarding screenshots written to {OUT}")


if __name__ == "__main__":
    main()
