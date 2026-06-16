from scalper.models import SearchQuery
from scalper.sources.base import REGISTRY
from scalper.sources.remoteok import RemoteOKAdapter
from scalper.sources.remotive import RemotiveAdapter

REMOTIVE_JOB = {
    "id": 998877,
    "url": "https://remotive.com/remote-jobs/backend/acme-998877",
    "title": "Senior Backend Engineer",
    "company_name": "Acme",
    "category": "Software Development",
    "tags": ["python", "aws"],
    "publication_date": "2026-06-10T12:00:00",
    "candidate_required_location": "Worldwide",
    "description": "<p>We use <strong>Python</strong> &amp; Postgres.</p>",
}

REMOTEOK_LEGAL = {"legal": "Use of this data requires attribution."}
REMOTEOK_JOB = {
    "slug": "backend-engineer-acme",
    "id": "112233",
    "epoch": 1717000000,
    "company": "Acme",
    "position": "Backend Engineer",
    "tags": ["python", "postgres"],
    "description": "<p>Build APIs in Python.</p>",
    "location": "Worldwide",
    "salary_min": 100000,
    "salary_max": 150000,
    "url": "https://remoteok.com/remote-jobs/112233",
}


def test_adapters_are_registered():
    assert REGISTRY["remotive"] is RemotiveAdapter
    assert REGISTRY["remoteok"] is RemoteOKAdapter


def test_remotive_normalizes_company_agnostic():
    p = RemotiveAdapter()._to_posting(REMOTIVE_JOB)
    assert p.source == "remotive"          # source is the platform, not a company
    assert p.source_id == "998877"
    assert p.company == "Acme"             # company comes from the posting, not config
    assert p.title == "Senior Backend Engineer"
    assert p.remote is True
    assert p.location == "Worldwide"
    assert p.published_at is not None and p.published_at.year == 2026
    assert "Python" in p.description and "<" not in p.description


def test_remotive_parses_free_text_salary():
    # Remotive emits salary as free text; the adapter should structure it.
    job = {**REMOTIVE_JOB, "salary": "$90k - $120k"}
    p = RemotiveAdapter()._to_posting(job)
    assert p.salary_min == 90000 and p.salary_max == 120000
    assert p.salary_currency == "USD"


def test_remotive_salary_absent_leaves_fields_none():
    p = RemotiveAdapter()._to_posting(REMOTIVE_JOB)  # no salary key
    assert p.salary_min is None and p.salary_max is None


def test_remoteok_normalizes_and_parses_salary():
    p = RemoteOKAdapter()._to_posting(REMOTEOK_JOB)
    assert p.source == "remoteok"
    assert p.source_id == "112233"
    assert p.company == "Acme"
    assert p.title == "Backend Engineer"
    assert p.remote is True
    assert p.salary_min == 100000 and p.salary_max == 150000
    assert p.salary_currency == "USD"
    assert p.published_at is not None


def test_remoteok_skips_legal_element_and_filters_by_terms():
    rows = [REMOTEOK_LEGAL, REMOTEOK_JOB]
    adapter = RemoteOKAdapter()
    # Simulate fetch's local filtering loop without hitting the network.
    kept = [
        adapter._to_posting(r)
        for r in rows
        if isinstance(r, dict) and "position" in r
    ]
    assert len(kept) == 1  # legal element dropped
    # A non-matching term should exclude the python posting.
    from scalper.sources._util import matches_any_term

    hay = f"{kept[0].title} {kept[0].description}"
    assert matches_any_term(hay, ["python"]) is True
    assert matches_any_term(hay, ["rust"]) is False
    assert matches_any_term(hay, []) is True  # no terms => keep everything


def test_remotive_unions_terms_field_default():
    q = SearchQuery(terms=["python", "go"])
    assert q.terms == ["python", "go"]
    assert q.remote is True and q.limit_per_source == 100
