"""Tests for the LLM Application Draft core (Phase 10)."""

from datetime import datetime, timezone

from scalper.app_draft import draft_application, draft_folder_name, slugify
from scalper.config import Profile, Weights
from scalper.models import JobPosting
from scalper.scoring import score_posting


class StubProvider:
    name = "stub"

    def __init__(self, reply):
        self._reply = reply
        self.calls = 0
        self.last_prompt = None
        self.last_system = None

    def complete(self, prompt, *, model, system=None, max_tokens=1024, temperature=0.2):
        self.calls += 1
        self.last_prompt = prompt
        self.last_system = system
        from scalper.llm.base import Completion

        return Completion(text=self._reply, model=model, input_tokens=50, output_tokens=20)


def _posting(**kw):
    base = dict(
        source="test", source_id="1", url="https://x/1", company="Acme",
        title="Backend Engineer", description="We use Python and Postgres.",
        remote=True, published_at=datetime.now(timezone.utc),
    )
    base.update(kw)
    return JobPosting(**base)


def _scored():
    profile = Profile(
        required_skills=["python", "postgres", "kafka"],
        weights=Weights(skill_coverage=1.0, title_match=0.0, keyword=0.0, semantic=0.0),
    )
    return score_posting(profile, _posting())


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Backend Engineer!!") == "backend-engineer"
    assert slugify("  ") == "untitled"


def test_draft_folder_name_combines_profile_position_and_uid():
    name = draft_folder_name("backend", "Senior Backend Engineer", "test::1")
    assert name == "backend_senior-backend-engineer_test-1"


_REPLY = "<<<RESUME>>>\n# Jane\n## SUMMARY\n- x\n<<<COVER_LETTER>>>\n# Jane\n\nHello.\n"


def test_draft_application_calls_provider_and_includes_skills_in_prompt():
    provider = StubProvider(_REPLY)
    scored = _scored()
    markdown, comp = draft_application(provider, "claude-sonnet-4-6", "backend", "Resume text.", scored)
    assert provider.calls == 1
    assert "python" in provider.last_prompt  # matched skill present
    assert "kafka" in provider.last_prompt  # missing skill present
    assert "Resume text." in provider.last_prompt
    assert "<<<RESUME>>>" in markdown
    assert "<<<COVER_LETTER>>>" in markdown
    assert comp.input_tokens == 50 and comp.output_tokens == 20


def test_draft_application_always_logs_request_and_response():
    provider = StubProvider(_REPLY)
    scored = _scored()
    logs = []
    draft_application(
        provider, "claude-sonnet-4-6", "backend", "Resume text.", scored, logger=logs.append
    )
    assert any("REQUEST" in line for line in logs)
    assert any("RESPONSE" in line for line in logs)


def test_draft_application_with_no_logger_does_not_raise():
    provider = StubProvider(_REPLY)
    draft_application(provider, "claude-sonnet-4-6", "backend", "Resume text.", _scored())
