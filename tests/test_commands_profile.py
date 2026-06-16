"""Tests for the `profile from-resume` command layer (Phase 9).

Purity contract: no argparse/print/exit — failures are `CommandError` subclasses,
success returns a typed `FromResumeResult`. A stub LLM provider stands in so these
run with no network and no `[llm]` extra. Resume is always passed explicitly via
the `resume` argument — there's no config-level fallback.
"""

import json

import pytest
import yaml

from scalper.commands.profile import (
    LLMUnavailableError,
    ProfileNameExistsError,
    ResumeNotFoundError,
    run_from_resume,
)
from scalper.config import Config, LLMConfig
from scalper.llm.base import REGISTRY, Completion


@pytest.fixture
def stub_provider(monkeypatch):
    reply = json.dumps({
        "titles": ["backend engineer"],
        "required_skills": ["python", "postgres"],
        "nice_to_have_skills": ["kafka"],
        "keywords": ["distributed systems"],
    })

    class StubProvider:
        name = "stub"

        def complete(self, prompt, *, model, system=None, max_tokens=1024, temperature=0.2):
            return Completion(text=reply, model=model, input_tokens=10, output_tokens=10)

    monkeypatch.setitem(REGISTRY, "anthropic", StubProvider)
    return StubProvider


def _config():
    return Config(llm=LLMConfig())


def test_missing_resume_file_raises(stub_provider, tmp_path):
    missing = tmp_path / "nope.md"
    with pytest.raises(ResumeNotFoundError):
        run_from_resume(_config(), "backend", str(missing))


def test_no_llm_provider_raises(tmp_path, monkeypatch):
    monkeypatch.setitem(REGISTRY, "anthropic", lambda: (_ for _ in ()).throw(ImportError()))
    p = tmp_path / "resume.md"
    p.write_text("Backend engineer, Python, Postgres.")
    with pytest.raises(LLMUnavailableError):
        run_from_resume(_config(), "backend", str(p))


def test_draft_only_returns_yaml_block_without_writing(stub_provider, tmp_path):
    p = tmp_path / "resume.md"
    p.write_text("Backend engineer, Python, Postgres, Kafka.")
    result = run_from_resume(_config(), "backend", str(p))
    assert result.written_to is None
    assert result.draft.titles == ["backend engineer"]
    parsed = yaml.safe_load(result.yaml_block)
    assert parsed["backend"]["required_skills"] == ["python", "postgres"]


def test_llm_call_is_always_logged(stub_provider, tmp_path):
    p = tmp_path / "resume.md"
    p.write_text("Backend engineer, Python, Postgres, Kafka.")
    info_lines: list[str] = []
    llm_lines: list[str] = []
    run_from_resume(_config(), "backend", str(p), on_info=info_lines.append, on_llm_log=llm_lines.append)

    # Usage/cost summary always goes through on_info...
    assert any("usage" in line.lower() for line in info_lines)
    # ...and the raw request/response always goes through on_llm_log.
    assert any("REQUEST" in line for line in llm_lines)
    assert any("RESPONSE" in line for line in llm_lines)


def test_llm_log_can_be_silenced_but_usage_summary_still_emitted(stub_provider, tmp_path):
    p = tmp_path / "resume.md"
    p.write_text("Backend engineer, Python, Postgres, Kafka.")
    info_lines: list[str] = []
    run_from_resume(_config(), "backend", str(p), on_info=info_lines.append, on_llm_log=None)
    assert any("usage" in line.lower() for line in info_lines)


def test_write_appends_under_profiles_preserving_comments(stub_provider, tmp_path):
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python, Postgres, Kafka.")

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "database: scalper.db\n"
        "# a helpful comment\n"
        "profiles:\n"
        "  existing:\n"
        "    titles:\n"
        "      - old role\n"
    )

    result = run_from_resume(
        _config(), "backend", str(resume), config_path=cfg_path, write=True,
    )
    assert result.written_to == cfg_path
    new_text = cfg_path.read_text()
    assert "# a helpful comment" in new_text  # comments survive the splice
    assert "old role" in new_text  # existing profile untouched

    data = yaml.safe_load(new_text)
    assert data["profiles"]["existing"]["titles"] == ["old role"]
    assert data["profiles"]["backend"]["required_skills"] == ["python", "postgres"]


def test_write_refuses_existing_name_without_force(stub_provider, tmp_path):
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python.")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("profiles:\n  backend:\n    titles:\n      - old\n")

    with pytest.raises(ProfileNameExistsError):
        run_from_resume(_config(), "backend", str(resume), config_path=cfg_path, write=True)


def test_write_force_overwrites_existing_name(stub_provider, tmp_path):
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python, Postgres.")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("profiles:\n  backend:\n    titles:\n      - old\n")

    run_from_resume(
        _config(), "backend", str(resume),
        config_path=cfg_path, write=True, force=True,
    )
    data = yaml.safe_load(cfg_path.read_text())
    assert data["profiles"]["backend"]["titles"] == ["backend engineer"]
    # The old profile had no hard filters set, so the defaults are appended.
    assert data["profiles"]["backend"]["remote_only"] is True
    assert data["profiles"]["backend"]["salary_floor"] == 0
    assert data["profiles"]["backend"]["freshness_days"] == 3
    assert data["profiles"]["backend"]["exclude_non_latin"] is True


def test_write_force_preserves_existing_hard_filters(stub_provider, tmp_path):
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python, Postgres.")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "profiles:\n"
        "  backend:\n"
        "    titles:\n"
        "      - old\n"
        "    remote_only: false\n"
        "    salary_floor: 80000\n"
    )

    run_from_resume(
        _config(), "backend", str(resume),
        config_path=cfg_path, write=True, force=True,
    )
    data = yaml.safe_load(cfg_path.read_text())
    backend = data["profiles"]["backend"]
    assert backend["titles"] == ["backend engineer"]  # re-drafted
    assert backend["remote_only"] is False  # kept, was already set
    assert backend["salary_floor"] == 80000  # kept, was already set
    assert backend["freshness_days"] == 3  # filled in, wasn't set before
    assert backend["exclude_non_latin"] is True  # filled in, wasn't set before


def test_write_force_only_touches_the_named_profile(stub_provider, tmp_path):
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python, Postgres.")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "database: scalper.db\n"
        "# a helpful comment\n"
        "llm:\n"
        "  provider: anthropic  # inline note\n"
        "profiles:\n"
        "  backend:\n"
        "    titles:\n"
        "      - old role\n"
        "  staff:\n"
        "    titles:\n"
        "      - staff engineer\n"
        "    weights:\n"
        "      skill_coverage: 0.45\n"
    )

    run_from_resume(
        _config(), "backend", str(resume),
        config_path=cfg_path, write=True, force=True,
    )
    new_text = cfg_path.read_text()

    # Everything outside the "backend" profile block is untouched, byte-for-byte.
    assert "# a helpful comment" in new_text
    assert "provider: anthropic  # inline note" in new_text

    data = yaml.safe_load(new_text)
    assert data["profiles"]["backend"]["titles"] == ["backend engineer"]
    # The unrelated "staff" profile survives the --force overwrite intact.
    assert data["profiles"]["staff"]["titles"] == ["staff engineer"]
    assert data["profiles"]["staff"]["weights"]["skill_coverage"] == 0.45


def test_write_with_no_existing_profiles_key(stub_provider, tmp_path):
    resume = tmp_path / "resume.md"
    resume.write_text("Backend engineer, Python.")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("database: scalper.db\n")

    run_from_resume(_config(), "backend", str(resume), config_path=cfg_path, write=True)
    data = yaml.safe_load(cfg_path.read_text())
    assert data["profiles"]["backend"]["titles"] == ["backend engineer"]
