"""Tests for the `draft` command layer (Phase 10).

Purity contract: no argparse/print/exit — failures are `CommandError` subclasses,
success returns a typed `DraftResult`. A stub LLM provider stands in so these run
with no network and no `[llm]` extra.
"""

import pytest

from scalper.commands.draft import (
    LLMUnavailableError,
    PostingNotFoundError,
    ProfileNotFoundError,
    ResumeNotFoundError,
    StoreNotFoundError,
    run_draft,
)
from scalper.config import Config, LLMConfig, Profile
from scalper.llm.base import REGISTRY, Completion
from scalper.models import JobPosting
from scalper.store import JobStore


_REPLY = (
    "<<<RESUME>>>\n"
    "# Jane Dev\n"
    "Backend Engineer\n"
    "Email: jane@example.com | Phone: +1 555\n\n"
    "## SUMMARY\n"
    "- Built scalable Python services.\n\n"
    "## PROFESSIONAL EXPERIENCE\n"
    "### Engineer | Acme :: 2020 – Present\n"
    "Led backend work.\n"
    "- **Services**: Built Python services.\n"
    "<<<COVER_LETTER>>>\n"
    "# Jane Dev\n"
    "Email: jane@example.com | Phone: +1 555\n\n"
    "Dear hiring team, I am excited to apply.\n"
)


@pytest.fixture
def stub_provider(monkeypatch):
    reply = _REPLY

    class StubProvider:
        name = "stub"

        def complete(self, prompt, *, model, system=None, max_tokens=1024, temperature=0.2):
            return Completion(text=reply, model=model, input_tokens=10, output_tokens=10)

    monkeypatch.setitem(REGISTRY, "anthropic", StubProvider)
    return StubProvider


def _config(**kw):
    base = dict(llm=LLMConfig(), profiles={"backend": Profile(required_skills=["python"])})
    base.update(kw)
    return Config(**base)


def _seed_store(db_path, uids=("a::1", "a::2")):
    with JobStore(str(db_path)) as store:
        postings = [
            JobPosting(
                source="a", source_id=uid.split("::")[1], url=f"https://x/{uid}",
                company="Acme", title=f"Backend Engineer {uid}",
                description="We use Python.", remote=True,
            )
            for uid in uids
        ]
        store.upsert_many(postings)
    return uids


def test_missing_resume_file_raises(stub_provider, tmp_path):
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path)
    config = _config(database=str(db_path))
    with pytest.raises(ResumeNotFoundError):
        run_draft(config, "backend", [uids[0]], str(tmp_path / "nope.md"))


def test_unknown_profile_raises(stub_provider, tmp_path):
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path)
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python.")
    config = _config(database=str(db_path))
    with pytest.raises(ProfileNotFoundError):
        run_draft(config, "nope", [uids[0]], str(resume))


def test_no_store_raises(stub_provider, tmp_path):
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python.")
    config = _config(database=str(tmp_path / "missing.db"))
    with pytest.raises(StoreNotFoundError):
        run_draft(config, "backend", ["a::1"], str(resume))


def test_unknown_uid_raises_listing_all_missing(stub_provider, tmp_path):
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path)
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python.")
    config = _config(database=str(db_path))
    with pytest.raises(PostingNotFoundError, match="nope-1.*nope-2|nope-1|nope-2"):
        run_draft(config, "backend", [uids[0], "nope-1", "nope-2"], str(resume))


def test_no_llm_provider_raises(tmp_path, monkeypatch):
    monkeypatch.setitem(REGISTRY, "anthropic", lambda: (_ for _ in ()).throw(ImportError()))
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path)
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python.")
    config = _config(database=str(db_path))
    with pytest.raises(LLMUnavailableError):
        run_draft(config, "backend", [uids[0]], str(resume))


def test_drafts_each_uid_into_its_own_folder_in_out_dir(stub_provider, tmp_path):
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path)
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python.")
    out_dir = tmp_path / "drafts"
    config = _config(database=str(db_path))

    result = run_draft(config, "backend", list(uids), str(resume), out_dir=str(out_dir))

    assert len(result.drafts) == 2
    for d in result.drafts:
        assert d.folder.parent == out_dir
        assert (d.folder / "resume.md").exists()
        assert (d.folder / "cover_letter.md").exists()
        assert "PROFESSIONAL EXPERIENCE" in (d.folder / "resume.md").read_text()
        assert "Dear hiring team" in (d.folder / "cover_letter.md").read_text()


def test_out_dir_arg_overrides_config_default(stub_provider, tmp_path):
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path)
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python.")
    config_default = tmp_path / "config_default_dir"
    arg_dir = tmp_path / "arg_dir"
    config = _config(database=str(db_path), draft_output_dir=str(config_default))

    result = run_draft(config, "backend", [uids[0]], str(resume), out_dir=str(arg_dir))

    assert result.drafts[0].folder.parent == arg_dir
    assert not config_default.exists()


def test_falls_back_to_config_draft_output_dir_when_no_out_arg(stub_provider, tmp_path):
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path)
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python.")
    config_default = tmp_path / "config_default_dir"
    config = _config(database=str(db_path), draft_output_dir=str(config_default))

    result = run_draft(config, "backend", [uids[0]], str(resume))

    assert result.drafts[0].folder.parent == config_default


def test_falls_back_to_drafts_under_output_dir_when_no_out_arg_or_config(
    stub_provider, tmp_path
):
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path)
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python.")
    config = _config(database=str(db_path), output_dir=str(tmp_path / "out"))

    result = run_draft(config, "backend", [uids[0]], str(resume))

    assert result.drafts[0].folder.parent.resolve() == (tmp_path / "out" / "drafts").resolve()


def test_folder_name_uses_profile_position_and_uid(stub_provider, tmp_path):
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path, uids=("a::1",))
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python.")
    config = _config(database=str(db_path))

    result = run_draft(config, "backend", [uids[0]], str(resume), out_dir=str(tmp_path))

    assert result.drafts[0].folder.name == "backend_backend-engineer-a-1_a-1"


def test_llm_call_is_always_logged(stub_provider, tmp_path):
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path)
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python.")
    config = _config(database=str(db_path))
    info_lines: list[str] = []
    llm_lines: list[str] = []

    run_draft(
        config, "backend", [uids[0]], str(resume), out_dir=str(tmp_path),
        on_info=info_lines.append, on_llm_log=llm_lines.append,
    )

    assert any("usage" in line.lower() for line in info_lines)
    assert any("REQUEST" in line for line in llm_lines)
    assert any("RESPONSE" in line for line in llm_lines)


def _register_reply(monkeypatch, reply):
    class StubProvider:
        name = "stub"

        def complete(self, prompt, *, model, system=None, max_tokens=1024, temperature=0.2):
            return Completion(text=reply, model=model, input_tokens=10, output_tokens=10)

    monkeypatch.setitem(REGISTRY, "anthropic", StubProvider)


def test_stretch_claims_file_written_only_when_present(monkeypatch, tmp_path):
    _register_reply(monkeypatch, _REPLY + "<<<STRETCH_CLAIMS>>>\n- Kubernetes (from Docker).\n")
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path, uids=("a::1",))
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer.")
    config = _config(database=str(db_path))

    result = run_draft(config, "backend", [uids[0]], str(resume), out_dir=str(tmp_path))

    d = result.drafts[0]
    assert d.has_stretch_claims
    assert (d.folder / "stretch_claims.md").read_text().startswith("- Kubernetes")


def test_no_stretch_claims_file_when_no_bridges(stub_provider, tmp_path):
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path, uids=("a::1",))
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer.")
    config = _config(database=str(db_path))

    result = run_draft(config, "backend", [uids[0]], str(resume), out_dir=str(tmp_path))

    d = result.drafts[0]
    assert not d.has_stretch_claims
    assert not (d.folder / "stretch_claims.md").exists()


def test_malformed_reply_is_a_per_posting_failure_with_no_folder(monkeypatch, tmp_path):
    _register_reply(monkeypatch, "no sentinels here, just prose")
    db_path = tmp_path / "store.db"
    uids = _seed_store(db_path, uids=("a::1",))
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer.")
    out_dir = tmp_path / "drafts"
    config = _config(database=str(db_path))

    result = run_draft(config, "backend", [uids[0]], str(resume), out_dir=str(out_dir))

    assert result.drafts == []
    assert len(result.failures) == 1 and result.failures[0][0] == "a::1"
    assert list(out_dir.glob("*")) == []  # no partial folder written
