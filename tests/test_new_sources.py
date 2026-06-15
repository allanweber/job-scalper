"""Offline parsing tests for the Phase-3 company-agnostic adapters.

Each sample payload below is trimmed from a real API/RSS response so the
normalization is exercised without touching the network.
"""

from scalper.sources._util import matches_any_term, rss_items
from scalper.sources.arbeitnow import ArbeitnowAdapter
from scalper.sources.base import REGISTRY
from scalper.sources.himalayas import HimalayasAdapter
from scalper.sources.jobicy import JobicyAdapter
from scalper.sources.themuse import TheMuseAdapter
from scalper.sources.weworkremotely import WeWorkRemotelyAdapter
from scalper.sources.workingnomads import WorkingNomadsAdapter


def test_all_new_adapters_registered():
    for key, cls in {
        "arbeitnow": ArbeitnowAdapter,
        "jobicy": JobicyAdapter,
        "themuse": TheMuseAdapter,
        "workingnomads": WorkingNomadsAdapter,
        "himalayas": HimalayasAdapter,
        "weworkremotely": WeWorkRemotelyAdapter,
    }.items():
        assert REGISTRY[key] is cls


ARBEITNOW_JOB = {
    "slug": "backend-engineer-acme-12345",
    "company_name": "Acme",
    "title": "Backend Engineer (Java)",
    "description": "<p>We build services in <strong>Java</strong> and Spring.</p>",
    "remote": True,
    "url": "https://www.arbeitnow.com/jobs/companies/acme/backend-engineer-12345",
    "tags": ["Java", "Spring"],
    "job_types": ["full-time"],
    "location": "Berlin",
    "created_at": 1781515835,
}


def test_arbeitnow_normalizes():
    p = ArbeitnowAdapter()._to_posting(ARBEITNOW_JOB)
    assert p.source == "arbeitnow"
    assert p.source_id == "backend-engineer-acme-12345"
    assert p.company == "Acme"
    assert p.title == "Backend Engineer (Java)"
    assert p.remote is True
    assert p.location == "Berlin"
    assert p.published_at is not None and p.published_at.year == 2026
    assert "Java" in p.description and "<" not in p.description


JOBICY_JOB = {
    "id": 146274,
    "url": "https://jobicy.com/jobs/146274-java-backend-engineer",
    "jobSlug": "146274-java-backend-engineer",
    "jobTitle": "Java Backend Engineer",
    "companyName": "Truelogic",
    "jobIndustry": ["Software Engineering"],
    "jobType": ["Full-Time"],
    "jobGeo": "LATAM",
    "jobLevel": "Senior",
    "jobExcerpt": "Build backend services.",
    "jobDescription": "<p>Work with <strong>Java</strong>.</p>",
    "pubDate": "2026-06-12T16:29:24+00:00",
}


def test_jobicy_normalizes_company_agnostic():
    p = JobicyAdapter()._to_posting(JOBICY_JOB)
    assert p.source == "jobicy"
    assert p.source_id == "146274"
    assert p.company == "Truelogic"   # company comes from the posting, not config
    assert p.title == "Java Backend Engineer"
    assert p.remote is True
    assert p.location == "LATAM"
    assert p.published_at is not None and p.published_at.year == 2026
    assert "Java" in p.description and "<" not in p.description


THEMUSE_JOB = {
    "id": 21303532,
    "name": "Senior Software Engineer",
    "contents": "<div><p>Build distributed systems in <b>Go</b>.</p></div>",
    "publication_date": "2026-05-29T18:34:01Z",
    "locations": [{"name": "Flexible / Remote"}],
    "categories": [{"name": "Software Engineering"}],
    "company": {"id": 15000190, "short_name": "acme", "name": "Acme"},
    "refs": {"landing_page": "https://www.themuse.com/jobs/acme/senior-software-engineer"},
}


def test_themuse_normalizes_and_detects_remote():
    p = TheMuseAdapter()._to_posting(THEMUSE_JOB)
    assert p.source == "themuse"
    assert p.source_id == "21303532"
    assert p.company == "Acme"
    assert p.title == "Senior Software Engineer"
    assert p.url.endswith("senior-software-engineer")
    assert p.remote is True                       # "Flexible / Remote" => remote
    assert p.location == "Flexible / Remote"
    assert "Go" in p.description and "<" not in p.description


def test_themuse_onsite_not_remote():
    onsite = {**THEMUSE_JOB, "locations": [{"name": "El Segundo, CA"}]}
    p = TheMuseAdapter()._to_posting(onsite)
    assert p.remote is False


WORKINGNOMADS_JOB = {
    "url": "https://www.workingnomads.com/job/go/1663269/",
    "title": "Senior Java Developer",
    "description": "<p>Backend in Java.</p>",
    "company_name": "Lemon.io",
    "category_name": "Development",
    "tags": "java,spring,postgres",
    "location": "Europe, North America",
    "pub_date": "2026-06-12T11:32:31-04:00",
}


def test_workingnomads_normalizes():
    p = WorkingNomadsAdapter()._to_posting(WORKINGNOMADS_JOB)
    assert p.source == "workingnomads"
    assert p.source_id == "https://www.workingnomads.com/job/go/1663269/"
    assert p.company == "Lemon.io"
    assert p.title == "Senior Java Developer"
    assert p.remote is True
    assert p.published_at is not None and p.published_at.year == 2026
    assert "Java" in p.description and "<" not in p.description


HIMALAYAS_JOB = {
    "title": "Backend Engineer",
    "companyName": "Avid",
    "companySlug": "avid",
    "description": "<div><p>Java and Kafka at scale.</p></div>",
    "minSalary": 120000,
    "maxSalary": 160000,
    "currency": "USD",
    "locationRestrictions": ["United States", "Canada"],
    "categories": ["Software-Engineering"],
    "pubDate": 1781517177,
    "applicationLink": "https://himalayas.app/companies/avid/jobs/backend-engineer",
    "guid": "https://himalayas.app/companies/avid/jobs/backend-engineer",
}


def test_himalayas_normalizes_and_parses_salary():
    p = HimalayasAdapter()._to_posting(HIMALAYAS_JOB)
    assert p.source == "himalayas"
    assert p.company == "Avid"
    assert p.title == "Backend Engineer"
    assert p.remote is True
    assert p.location == "United States, Canada"
    assert p.salary_min == 120000 and p.salary_max == 160000
    assert p.salary_currency == "USD"
    assert p.published_at is not None and p.published_at.year == 2026
    assert "Java" in p.description and "<" not in p.description


WWR_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>We Work Remotely</title>
    <item>
      <title>Acme: Senior Java Engineer</title>
      <region>Anywhere in the World</region>
      <category>Back-End Programming</category>
      <description>&lt;p&gt;Build services in &lt;strong&gt;Java&lt;/strong&gt;.&lt;/p&gt;</description>
      <pubDate>Thu, 21 May 2026 20:03:04 +0000</pubDate>
      <guid>https://weworkremotely.com/remote-jobs/acme-senior-java-engineer-1</guid>
      <link>https://weworkremotely.com/remote-jobs/acme-senior-java-engineer-1</link>
    </item>
  </channel>
</rss>"""


def test_weworkremotely_parses_rss_and_splits_company_title():
    items = rss_items(WWR_RSS)
    assert len(items) == 1
    p = WeWorkRemotelyAdapter()._to_posting(items[0])
    assert p.source == "weworkremotely"
    assert p.company == "Acme"                    # split from "Company: Role"
    assert p.title == "Senior Java Engineer"
    assert p.remote is True
    assert p.location == "Anywhere in the World"
    assert p.url.endswith("acme-senior-java-engineer-1")
    assert p.published_at is not None and p.published_at.year == 2026
    assert "Java" in p.description and "<" not in p.description


def test_broad_feed_term_filtering_for_java():
    p = WorkingNomadsAdapter()._to_posting(WORKINGNOMADS_JOB)
    hay = f"{p.title} {p.description} {WORKINGNOMADS_JOB['tags']}"
    assert matches_any_term(hay, ["java"]) is True
    assert matches_any_term(hay, ["rust"]) is False
