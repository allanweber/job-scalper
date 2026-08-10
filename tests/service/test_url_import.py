from __future__ import annotations

import pytest

from scalper.service.url_import import (
    UrlImportError,
    _guard_public_host,
    build_posting_from_text,
    import_posting_from_text,
    import_posting_from_url,
    parse_posting,
)

_HTML = """
<html><head>
  <title>Senior Platform Engineer — Railbird</title>
  <meta property="og:site_name" content="Railbird">
  <meta property="og:description" content="Own our Kubernetes platform.">
</head><body>
  <p>Fully remote role. You will own our Kubernetes platform end to end,
  running kubernetes and terraform on aws for a fast-growing product team,
  building the tooling other engineers depend on every single day.</p>
  <p>Compensation $130,000 – 160,000 USD plus equity.</p>
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
    html = ("<html><head><title>Backend Engineer</title></head><body>"
            "We are hiring a backend engineer to design and ship the APIs at the "
            "core of our product, working in Python across a modern cloud stack "
            "with a small senior team that ships every week.</body></html>")
    p = parse_posting("https://www.acme-jobs.io/x", html)
    assert p.company == "Acme-Jobs"  # derived from the domain when no og:site_name


def test_parse_rejects_titleless_page():
    with pytest.raises(UrlImportError):
        parse_posting("https://x.example/y", "<html><body>no title here</body></html>")


def test_parse_rejects_js_app_shell():
    # A single-page-app apply page: a title but no readable job content in the
    # server-rendered HTML. We refuse rather than pool a contentless posting.
    html = ("<html><head><title>Career Website</title></head>"
            "<body><div id=\"root\">Career Website</div>"
            "<script>window.__DATA__={}</script></body></html>")
    with pytest.raises(UrlImportError, match="JavaScript"):
        parse_posting("https://people-jobs.example/apply/abc", html)


def test_parse_reads_json_ld_job_posting():
    # ATS/career pages often render the body client-side but still embed the
    # posting as schema.org JSON-LD — which must win over the empty app shell.
    html = """
    <html><head>
      <title>Careers</title>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"JobPosting",
       "title":"Staff Backend Engineer",
       "description":"<p>Build <b>distributed</b> systems in Python and Go at large scale. You will own critical backend services end to end, mentor the wider engineering team, and shape our platform roadmap over the coming year.</p>",
       "hiringOrganization":{"@type":"Organization","name":"Huspy"},
       "jobLocationType":"TELECOMMUTE",
       "baseSalary":{"@type":"MonetaryAmount","currency":"USD",
         "value":{"@type":"QuantitativeValue","minValue":150000,"maxValue":190000}}}
      </script>
    </head><body><div id="root"></div></body></html>
    """
    p = parse_posting("https://people-jobs.example/huspy/apply/abc", html)
    assert p.title == "Staff Backend Engineer"       # from JSON-LD, not <title>
    assert p.company == "Huspy"
    assert "distributed systems" in p.description.lower()
    assert "<b>" not in p.description                 # HTML stripped
    assert p.remote is True                           # TELECOMMUTE
    assert p.salary_min == 150000 and p.salary_max == 190000
    assert p.salary_currency == "USD"


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


_PASTED = (
    "We are hiring a Senior Backend Engineer to build distributed payment "
    "systems in Python and Go. Remote-friendly. You will own critical services "
    "end to end, mentor teammates, and shape the platform. Salary $140,000 - "
    "180,000 USD."
)


def test_build_from_text_derives_title_and_fields():
    p = build_posting_from_text(_PASTED)
    # No title given → taken from the first line of the pasted text.
    assert p.title.startswith("We are hiring a Senior Backend Engineer")
    assert p.company == "Pasted posting"        # no url/company → generic label
    assert p.remote is True
    assert p.salary_min == 140000 and p.salary_max == 180000
    assert "distributed payment" in p.description.lower()
    assert p.source == "url"


def test_build_from_text_uses_explicit_title_and_url_company():
    p = build_posting_from_text(_PASTED, title="Staff Engineer",
                                url="https://boards.greenhouse.io/acme/jobs/9")
    assert p.title == "Staff Engineer"
    assert p.company == "Boards"                 # from the URL host
    assert p.url == "https://boards.greenhouse.io/acme/jobs/9"


def test_build_from_text_rejects_too_short():
    with pytest.raises(UrlImportError, match="too short"):
        build_posting_from_text("Backend engineer wanted.")


def test_import_from_text_pools_and_is_fetchable(conn):
    pid = import_posting_from_text(conn, _PASTED, company="Acme")
    from scalper.service.content_repos import PostingRepo
    stored = PostingRepo(conn).get(pid)
    assert stored is not None and stored.company == "Acme"
    assert stored.sources == ["url"]


def test_import_ingests_via_injected_fetcher(conn):
    pid = import_posting_from_url(
        conn, "https://railbird.example/careers/9", fetcher=lambda _u: _HTML)
    from scalper.service.content_repos import PostingRepo
    stored = PostingRepo(conn).get(pid)
    assert stored is not None and stored.title.startswith("Senior Platform Engineer")
    assert stored.sources == ["url"]
