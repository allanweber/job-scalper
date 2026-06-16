"""Phase 6: the command layer (`scalper.commands`) is callable without the CLI.

Each test drives a command function directly — no argparse, no CLI — and asserts on
its typed result and its injected callbacks, proving the logic is front-end-ready.
"""

import pytest

from scalper.commands import CommandError
from scalper.commands.collect import NoSourcesError, run_collect
from scalper.commands.report import ProfileNotFoundError, StoreNotFoundError, run_report
from scalper.commands.sources import run_sources
from scalper.config import Config, Profile, SourceConfig, Weights
from scalper.models import JobPosting, SearchQuery
from scalper.sources.base import REGISTRY, SourceAdapter
from scalper.store import JobStore


# --- a tiny in-memory adapter so collect can run without the network ---------

class _StubAdapter(SourceAdapter):
    type = "stub"

    @property
    def name(self) -> str:
        return "stub"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        return [
            JobPosting(source="stub", source_id="1", url="https://x/1", company="Co",
                       title="Backend Engineer", description="Python.", remote=True),
            JobPosting(source="stub", source_id="2", url="https://x/2", company="Co",
                       title="Data Engineer", description="SQL.", remote=True),
        ]


@pytest.fixture
def stub_source():
    REGISTRY["stub"] = _StubAdapter
    try:
        yield
    finally:
        REGISTRY.pop("stub", None)


def _config(tmp_path, sources=None):
    return Config(
        database=str(tmp_path / "s.db"),
        search=SearchQuery(terms=["python"]),
        sources=sources or [],
        profiles={"backend": Profile(titles=["backend engineer"],
                                     required_skills=["python"],
                                     weights=Weights(skill_coverage=1.0))},
    )


# --- run_collect -----------------------------------------------------------

def test_run_collect_populates_store(tmp_path, stub_source):
    cfg = _config(tmp_path, [SourceConfig(type="stub")])
    infos: list[str] = []
    result = run_collect(cfg, on_info=infos.append)
    assert result.total_new == 2
    assert result.total_stored == 2
    assert [(o.name, o.fetched, o.new) for o in result.outcomes] == [("stub", 2, 2)]
    assert any("stub" in m for m in infos)


def test_run_collect_no_sources_raises(tmp_path):
    with pytest.raises(NoSourcesError):
        run_collect(_config(tmp_path, []))


def test_run_collect_unknown_filter_warns_then_raises(tmp_path, stub_source):
    cfg = _config(tmp_path, [SourceConfig(type="stub")])
    warns: list[str] = []
    with pytest.raises(NoSourcesError):
        run_collect(cfg, only_sources=["nope"], on_warning=warns.append)
    assert any("nope" in w for w in warns)


# --- run_report ------------------------------------------------------------

def _seed(db):
    with JobStore(db) as store:
        store.upsert_many([
            JobPosting(source="stub", source_id="1", url="https://x/1", company="Co",
                       title="Backend Engineer", description="Python and Django.", remote=True),
        ])


def test_run_report_renders_without_cli(tmp_path):
    cfg = _config(tmp_path)
    _seed(cfg.database)
    result = run_report(cfg, "backend", semantic=False)
    assert result.profile_name == "backend"
    assert "<html" in result.html.lower()
    assert result.total_considered == 1
    assert result.matched == 1
    assert result.scored[0].percent > 0


def test_run_report_unknown_profile_raises(tmp_path):
    cfg = _config(tmp_path)
    _seed(cfg.database)
    with pytest.raises(ProfileNotFoundError):
        run_report(cfg, "ghost", semantic=False)


def test_run_report_no_store_raises(tmp_path):
    with pytest.raises(StoreNotFoundError):
        run_report(_config(tmp_path), "backend", semantic=False)


def test_command_errors_share_a_base():
    assert issubclass(NoSourcesError, CommandError)
    assert issubclass(ProfileNotFoundError, CommandError)
    assert issubclass(StoreNotFoundError, CommandError)


# --- run_sources -----------------------------------------------------------

def test_run_sources_cross_references(tmp_path, stub_source):
    cfg = _config(tmp_path, [SourceConfig(type="stub")])
    _seed(cfg.database)
    result = run_sources(cfg)
    assert result.total_stored == 1
    assert [r.type for r in result.configured] == ["stub"]
    assert result.configured[0].stored == 1
    # every other registered adapter shows up as unconfigured
    assert "remotive" in result.registered_unconfigured
