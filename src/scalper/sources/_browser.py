"""Shared headless-browser helper for the 'hard' source tier (Phase 4).

LinkedIn and Indeed actively resist automation, so there's no structured API to
parse. These sources are scraped with a self-hosted headless browser
(Playwright), **anonymously only — never with the user's own credentials** — and
at low frequency. Treat them as fragile gap-fillers, not the backbone: every
fetch fails soft (logs and returns nothing) so a blocked or broken hard source
never aborts a `collect` run.

Playwright is an optional dependency behind the `[scrape]` extra. Import this
module freely: the browser is only imported when a session is actually opened,
so the hard adapters can register and the report can render without `[scrape]`
installed.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Callable

# A realistic desktop Chrome UA. We browse anonymously: no account, no cookies,
# no login — just an unauthenticated visitor like any guest hitting a public page.
_DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# Hides the most obvious automation tell (navigator.webdriver). This is not a
# serious anti-detection arms race — hard sources are expected to block sometimes.
_STEALTH_JS = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"

#: A callable that takes a URL and returns rendered HTML (or None on failure).
#: Adapters depend on this shape so tests can inject canned pages without a browser.
Fetcher = Callable[[str], "str | None"]


def wait_until_cleared(
    get_content: Callable[[], "str | None"],
    is_blocked: Callable[[str], bool],
    *,
    timeout: float,
    poll: float,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> "str | None":
    """Poll `get_content` until it stops looking blocked, or `timeout` elapses.

    This handles the *legitimate* cases only: a passive JS challenge that a real
    browser clears on its own, or — in a headful, persistent session — a human
    solving an interactive challenge by hand in the visible window. It never
    *solves* anything; it just waits and returns whatever finally rendered (the
    last non-empty content if the challenge never clears). `timeout <= 0` returns
    the first read immediately (the prior fast-bail behaviour).
    """
    content = get_content()
    if timeout <= 0:
        return content
    if content and not is_blocked(content):
        return content
    deadline = now() + timeout
    while now() < deadline:
        sleep(poll)
        latest = get_content()
        if latest and not is_blocked(latest):
            return latest
        if latest:
            content = latest  # remember the last non-empty page we saw
    return content


def _debug_dump(url: str, html: str | None) -> None:
    """If SCALPER_DEBUG_HTML is set, write the rendered page there for inspection.

    A 'hard' source returning nothing is almost always markup drift, not a real
    block. Dumping the actual HTML lets us see whether the expected blob/selector
    is still present or was renamed, without guessing.
    """
    dest = os.environ.get("SCALPER_DEBUG_HTML")
    if not dest or not html:
        return
    try:
        out = Path(dest)
        out.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", url)[:80].strip("-") or "page"
        path = out / f"{slug}-{int(time.time() * 1000)}.html"
        path.write_text(html, encoding="utf-8")
        print(f"    browser: wrote {len(html):,} bytes to {path}")
    except Exception:  # noqa: BLE001 — debugging aid must never break a run
        pass


def playwright_available() -> bool:
    """True if the `[scrape]` extra (Playwright) is importable."""
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:  # noqa: BLE001 — any import error means the extra is unusable
        return False
    return True


class BrowserSession:
    """A short-lived anonymous headless browser, opened as a context manager.

    Politeness is built in: `delay` seconds between successive `get`s, a single
    retry with backoff on failure, and a hard per-navigation `timeout`. `get`
    never raises — it returns the rendered HTML or None, so a hostile or blocked
    page degrades to "no postings" instead of crashing the collect run.

    `headless=False` opens a visible window (so a human can solve an interactive
    challenge themselves) and `user_data_dir` keeps a persistent profile, so the
    cookies from a cleared challenge survive across runs. Neither defeats a
    challenge automatically — see `wait_until_cleared`.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout: float = 30.0,
        delay: float = 2.0,
        max_retries: int = 1,
        locale: str = "en-US",
        user_agent: str | None = None,
        user_data_dir: str | None = None,
        challenge_timeout: float = 0.0,
        challenge_poll: float = 2.0,
        log: Callable[[str], None] | None = None,
    ):
        self.headless = headless
        self.timeout = timeout
        self.delay = delay
        self.max_retries = max_retries
        self.locale = locale
        self.user_agent = user_agent or _DEFAULT_UA
        # A persistent profile dir reuses cookies/storage across runs, so a
        # challenge cleared once (by a real browser or a human) tends to stay clear.
        self.user_data_dir = user_data_dir
        # How long to wait for a challenge to clear before giving up, and the
        # poll interval. 0 keeps the old fast-bail behaviour.
        self.challenge_timeout = challenge_timeout
        self.challenge_poll = challenge_poll
        self._log = log or (lambda _m: None)
        self._pw = self._browser = self._context = self._page = None
        self._used = False  # have we fetched once? (controls the inter-get delay)

    def __enter__(self) -> "BrowserSession":
        from playwright.sync_api import sync_playwright  # lazy: needs [scrape]

        self._pw = sync_playwright().start()
        launch_args = {"args": ["--disable-blink-features=AutomationControlled"]}
        context_args = {
            "user_agent": self.user_agent,
            "locale": self.locale,
            "viewport": {"width": 1366, "height": 768},
        }
        if self.user_data_dir:
            # A persistent context bundles its own browser; there's no separate
            # browser object to close.
            self._context = self._pw.chromium.launch_persistent_context(
                self.user_data_dir, headless=self.headless, **launch_args, **context_args
            )
            self._page = (
                self._context.pages[0]
                if self._context.pages
                else self._context.new_page()
            )
        else:
            self._browser = self._pw.chromium.launch(
                headless=self.headless, **launch_args
            )
            self._context = self._browser.new_context(**context_args)
            self._page = self._context.new_page()
        self._context.add_init_script(_STEALTH_JS)
        self._page.set_default_timeout(self.timeout * 1000)
        return self

    def __exit__(self, *exc: object) -> None:
        for closer in (self._context, self._browser):
            try:
                if closer is not None:
                    closer.close()
            except Exception:  # noqa: BLE001 — teardown must not raise
                pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass

    def get(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        wait_selector: str | None = None,
        is_blocked: Callable[[str], bool] | None = None,
    ) -> str | None:
        """Navigate to `url`, return the rendered HTML, or None on failure.

        If `is_blocked` is given and the first render looks blocked, wait up to
        `challenge_timeout` for it to clear (a passive JS challenge resolves on
        its own; a headful session lets a human solve an interactive one).
        """
        from playwright.sync_api import Error as PlaywrightError  # lazy

        def _content() -> str:
            try:
                return self._page.content()
            except PlaywrightError:
                return ""  # transient (mid-reload) — treated as "keep waiting"

        for attempt in range(self.max_retries + 1):
            if self._used:
                time.sleep(self.delay)  # polite gap between navigations
            self._used = True
            try:
                self._page.goto(url, wait_until=wait_until)
                if wait_selector:
                    try:
                        self._page.wait_for_selector(
                            wait_selector, timeout=self.timeout * 1000
                        )
                    except PlaywrightError:
                        # Selector never appeared — usually a block page or an
                        # empty result set. Fall through; clearance-wait (if any)
                        # gets a chance, then the parser fails soft.
                        pass
                if is_blocked is not None and self.challenge_timeout > 0 and is_blocked(_content()):
                    self._log(
                        f"    browser: challenge at {url} — waiting up to "
                        f"{self.challenge_timeout:.0f}s for it to clear"
                        + (" (solve it in the window if shown)" if not self.headless else "")
                    )
                    cleared = wait_until_cleared(
                        _content, is_blocked,
                        timeout=self.challenge_timeout, poll=self.challenge_poll,
                    )
                    _debug_dump(url, cleared)
                    return cleared
                html = _content()
                _debug_dump(url, html)
                return html
            except PlaywrightError as exc:
                if attempt < self.max_retries:
                    time.sleep(self.delay * (attempt + 2))
                    continue
                self._log(f"    browser: {url} failed ({type(exc).__name__}); skipping.")
                return None
        return None
