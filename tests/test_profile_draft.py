"""Tests for the LLM resume->profile extraction core (Phase 9)."""

import json

from scalper.profile_draft import (
    ProfileDraft,
    draft_profile,
    parse_draft,
    profile_fields,
    to_yaml_block,
)


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

        return Completion(text=self._reply, model=model, input_tokens=50, output_tokens=10)


def test_parse_clean_json():
    text = json.dumps({
        "titles": ["backend engineer"],
        "required_skills": ["python", "postgres"],
        "nice_to_have_skills": ["kafka"],
        "keywords": ["distributed systems"],
    })
    draft = parse_draft(text)
    assert draft.titles == ["backend engineer"]
    assert draft.required_skills == ["python", "postgres"]
    assert draft.nice_to_have_skills == ["kafka"]
    assert draft.keywords == ["distributed systems"]


def test_parse_tolerates_surrounding_prose_and_fences():
    text = f'Here you go:\n```json\n{json.dumps({"titles": ["engineer"]})}\n```'
    draft = parse_draft(text)
    assert draft.titles == ["engineer"]


def test_parse_unparseable_fails_soft_to_empty():
    draft = parse_draft("not json at all")
    assert draft == ProfileDraft()


def test_draft_profile_calls_provider_and_parses():
    reply = json.dumps({"titles": ["sre"], "required_skills": ["kubernetes"]})
    provider = StubProvider(reply)
    draft, comp = draft_profile(provider, "claude-sonnet-4-6", "Resume text about SRE work.")
    assert provider.calls == 1
    assert "Resume text about SRE work." in provider.last_prompt
    assert draft.titles == ["sre"]
    assert draft.required_skills == ["kubernetes"]
    assert comp.input_tokens == 50 and comp.output_tokens == 10


def test_draft_profile_always_logs_request_and_response():
    reply = json.dumps({"titles": ["sre"]})
    provider = StubProvider(reply)
    logs = []
    draft_profile(provider, "claude-sonnet-4-6", "Resume text.", logger=logs.append)
    assert any("REQUEST" in line for line in logs)
    assert any("RESPONSE" in line for line in logs)
    assert any("Resume text." in line for line in logs)


def test_draft_profile_with_no_logger_does_not_raise():
    reply = json.dumps({"titles": ["sre"]})
    provider = StubProvider(reply)
    draft_profile(provider, "claude-sonnet-4-6", "Resume text.")  # logger=None default


def test_compound_skills_are_split_into_separate_items():
    text = json.dumps({
        "required_skills": ["python / pandas data pipelines", "docker / ci-cd pipelines"],
        "nice_to_have_skills": ["mongodb / postgres / redis"],
    })
    draft = parse_draft(text)
    assert draft.required_skills == [
        "python", "pandas data pipelines", "docker", "ci-cd pipelines",
    ]
    assert draft.nice_to_have_skills == ["mongodb", "postgres", "redis"]


def test_to_yaml_block_is_parseable_and_nested_under_name():
    import yaml

    draft = ProfileDraft(titles=["backend engineer"], required_skills=["python"])
    block = to_yaml_block("backend", draft)
    parsed = yaml.safe_load(block)
    assert parsed == {
        "backend": {
            "titles": ["backend engineer"],
            "required_skills": ["python"],
            "nice_to_have_skills": [],
            "keywords": [],
            "remote_only": True,
            "salary_floor": 0,
            "exclude_non_latin": True,
        }
    }


def test_drafted_profile_always_gets_default_hard_filters():
    draft = ProfileDraft(titles=["sre"])
    fields = profile_fields(draft)
    assert fields["remote_only"] is True
    assert fields["salary_floor"] == 0
    assert "freshness_days" not in fields  # global setting, not per-profile
    assert fields["exclude_non_latin"] is True
