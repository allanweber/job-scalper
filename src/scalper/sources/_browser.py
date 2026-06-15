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

import time
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
        log: Callable[[str], None] | None = None,
    ):
        self.headless = headless
        self.timeout = timeout
        self.delay = delay
        self.max_retries = max_retries
        self.locale = locale
        self.user_agent = user_agent or _DEFAULT_UA
        self._log = log or (lambda _m: None)
        self._pw = self._browser = self._context = self._page = None
        self._used = False  # have we fetched once? (controls the inter-get delay)

    def __enter__(self) -> "BrowserSession":
        from playwright.sync_api import sync_playwright  # lazy: needs [scrape]

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = self._browser.new_context(
            user_agent=self.user_agent,
            locale=self.locale,
            viewport={"width": 1366, "height": 768},
        )
        self._context.add_init_script(_STEALTH_JS)
        self._page = self._context.new_page()
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
    ) -> str | None:
        """Navigate to `url`, return the rendered HTML, or None on failure."""
        from playwright.sync_api import Error as PlaywrightError  # lazy

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
                        # empty result set. Return whatever rendered; the
                        # adapter's parser will find nothing and fail soft.
                        pass
                return self._page.content()
            except PlaywrightError as exc:
                if attempt < self.max_retries:
                    time.sleep(self.delay * (attempt + 2))
                    continue
                self._log(f"    browser: {url} failed ({type(exc).__name__}); skipping.")
                return None
        return None
