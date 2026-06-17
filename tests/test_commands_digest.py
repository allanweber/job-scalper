"""Phase 11: `digest` collects, then reports only the Fresh Catch (ADR 0005).

A posting already in the store before this run is excluded even if the source
returns it again; only postings whose first-seen `collected_at` lands at or
after this run's `run_start` are scored/rendered.
"""

import pytest

from scalper.commands import CommandError
from scalper.commands.digest import NoProfilesError, ProfileNotFoundError, run_digest
from scalper.config import Config, Profile, SourceConfig, Weights
from scalper.models import JobPosting, SearchQuery
from scalper.sources.base import REGISTRY, SourceAdapter
from scalper.store import JobStore


class _StubAdapter(SourceAdapter):
    type = "stub"

    @property
    def name(self) -> str:
        return "stub"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        return [
            # Already in the store before this run — re-appearing here must
            # not count as Fresh Catch (collected_at is preserved by upsert).
            JobPosting(source="stub", source_id="old", url="https://x/old", company="Co",
                       title="Backend Engineer", description="Python.", remote=True),
            # Genuinely new this run.
            JobPosting(source="stub", source_id="new", url="https://x/new", company="Co",
                       title="Backend Engineer II", description="Python and Django.", remote=True),
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
        sources=sources or [SourceConfig(type="stub")],
        profiles={"backend": Profile(titles=["backend engineer"],
                                     required_skills=["python"],
                                     weights=Weights(skill_coverage=1.0))},
    )


def _seed_existing(db):
    with JobStore(db) as store:
        store.upsert_many([
            JobPosting(source="stub", source_id="old", url="https://x/old", company="Co",
                       title="Backend Engineer", description="Python.", remote=True),
        ])


def test_run_digest_excludes_already_stored_posting(tmp_path, stub_source):
    cfg = _config(tmp_path)
    _seed_existing(cfg.database)
    result = run_digest(cfg, ["backend"], semantic=False)
    assert result.total_new == 1  # only the genuinely new posting
    assert result.profiles[0].profile_name == "backend"
    assert result.profiles[0].new == 1
    assert "Backend Engineer II" in result.html
    assert "Backend Engineer</" not in result.html  # the stale one isn't rendered


def test_run_digest_first_run_includes_everything(tmp_path, stub_source):
    cfg = _config(tmp_path)
    result = run_digest(cfg, ["backend"], semantic=False)
    assert result.total_new == 2
    assert result.profiles[0].new == 2


def test_run_digest_zero_new_is_clean(tmp_path, stub_source):
    cfg = _config(tmp_path)
    _seed_existing(cfg.database)
    with JobStore(cfg.database) as store:
        store.upsert_many([
            JobPosting(source="stub", source_id="new", url="https://x/new", company="Co",
                       title="Backend Engineer II", description="Python and Django.", remote=True),
        ])

    # Both postings the stub returns are already in the store, so nothing is
    # Fresh Catch this run.
    result = run_digest(cfg, ["backend"], semantic=False)
    assert result.total_new == 0
    assert result.profiles[0].new == 0
    assert "<html" in result.html.lower()


def test_run_digest_all_profiles_renders_tabs(tmp_path, stub_source):
    cfg = _config(tmp_path)
    cfg.profiles["niche"] = Profile(titles=["rust"], required_skills=["rust"],
                                    exclude_keywords=["python"])
    result = run_digest(cfg, list(cfg.profiles), semantic=False)
    assert len(result.profiles) == 2
    by_name = {p.profile_name: p for p in result.profiles}
    assert by_name["backend"].new == 2
    assert by_name["niche"].new == 0
    assert 'data-target="backend"' in result.html
    assert 'data-target="niche"' in result.html


def test_run_digest_unknown_profile_raises(tmp_path, stub_source):
    cfg = _config(tmp_path)
    with pytest.raises(ProfileNotFoundError):
        run_digest(cfg, ["ghost"], semantic=False)


def test_run_digest_no_profiles_raises(tmp_path):
    cfg = _config(tmp_path)
    with pytest.raises(NoProfilesError):
        run_digest(cfg, [], semantic=False)


def test_digest_errors_share_command_error_base():
    assert issubclass(ProfileNotFoundError, CommandError)
    assert issubclass(NoProfilesError, CommandError)
