from __future__ import annotations

import pytest

from scalper.service.url_import import (
    UrlImportError,
    _guard_public_host,
    import_posting_from_url,
    parse_posting,
)

_HTML = """
<html><head>
  <title>Senior Platform Engineer — Railbird</title>
  <meta property="og:site_name" content="Railbird">
  <meta property="og:description" content="Own our Kubernetes platform.">
</head><body>
  Fully remote. Compensation $130,000 – 160,000 USD. kubernetes terraform aws.
</body></html>
"""


def test_parse_extracts_core_fields():
    p = parse_posting("https://railbird.example/careers/9", _HTML)
    assert p.title == "Senior Platform Engineer — Railbird"
    assert p.company == "Railbird"
    assert p.remote is True
    assert p.salary_min == 130000 and p.salary_max == 160000
    assert p.salary_currency == "USD"
    assert "kubernetes" in p.description.lower()
    assert p.source == "url" and p.source_id == "https://railbird.example/careers/9"


def test_parse_falls_back_to_domain_for_company():
    html = "<html><head><title>Backend Engineer</title></head><body>work here</body></html>"
    p = parse_posting("https://www.acme-jobs.io/x", html)
    assert p.company == "Acme-Jobs"  # derived from the domain when no og:site_name


def test_parse_rejects_titleless_page():
    with pytest.raises(UrlImportError):
        parse_posting("https://x.example/y", "<html><body>no title here</body></html>")


@pytest.mark.parametrize("url", [
    "ftp://example.com/x",           # non-http scheme
    "http://localhost/x",            # loopback
    "http://127.0.0.1/x",            # loopback ip
    "http://169.254.169.254/latest", # link-local (cloud metadata)
    "http://10.0.0.5/x",             # private
    "http://192.168.1.1/x",          # private
])
def test_ssrf_guard_blocks_non_public_targets(url):
    with pytest.raises(UrlImportError):
        _guard_public_host(url)


def test_import_ingests_via_injected_fetcher(conn):
    pid = import_posting_from_url(
        conn, "https://railbird.example/careers/9", fetcher=lambda _u: _HTML)
    from scalper.service.content_repos import PostingRepo
    stored = PostingRepo(conn).get(pid)
    assert stored is not None and stored.title.startswith("Senior Platform Engineer")
    assert stored.sources == ["url"]
