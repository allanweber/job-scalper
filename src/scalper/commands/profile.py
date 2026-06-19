"""`profile from-resume` command core: draft a Profile from a given Resume file.

Follows the purity contract (no argparse/print/exit): failures raise `CommandError`
subclasses instead of printing a hint directly, so the CLI can render them uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

from scalper.commands import CommandError
from scalper.config import Config
from scalper.enrich import Usage, format_usage
from scalper.llm import build_provider
from scalper.profile_draft import (
    DEFAULT_PROFILE_SETTINGS,
    ProfileDraft,
    draft_profile,
    profile_fields,
    to_yaml_block,
    to_yaml_block_from_fields,
)
from scalper.resume import load_resume


def _noop(_msg: str) -> None:
    pass


class ResumeNotFoundError(CommandError):
    """The given resume file does not exist."""


class LLMUnavailableError(CommandError):
    """No LLM provider available (missing `[llm]` extra or API key)."""


class ProfileNameExistsError(CommandError):
    """Refuses to silently overwrite an existing profile name without `--force`."""


@dataclass
class FromResumeResult:
    name: str
    draft: ProfileDraft
    yaml_block: str
    written_to: Path | None = None


def _load_resume_text(resume: str | Path) -> str:
    try:
        return load_resume(resume)
    except FileNotFoundError as e:
        raise ResumeNotFoundError(str(e)) from None


def _find_block(
    lines: list[str], start: int, end: int, indent: str, key_line: str
) -> tuple[int, int] | None:
    """Find a `key_line` at exactly `indent` within `lines[start:end]`.

    Returns `(block_start, block_end)` where `block_end` is the line index of
    the next sibling at the same indent (blank lines/comments are skipped), or
    `end` if the block runs to the end of the search range.
    """
    target = indent + key_line
    for i in range(start, end):
        if lines[i].rstrip("\n") == target:
            block_end = end
            for j in range(i + 1, end):
                stripped = lines[j].rstrip("\n")
                if stripped.strip() == "" or stripped.lstrip().startswith("#"):
                    continue
                cur_indent = len(stripped) - len(stripped.lstrip())
                if cur_indent <= len(indent):
                    block_end = j
                    break
            return i, block_end
    return None


def _splice_under_profiles(text: str, indented_block: str) -> str:
    """Insert `indented_block` as the last entry of the file's `profiles:` map.

    Pure text splice (no full re-parse/re-dump) so existing comments survive. If
    there's no `profiles:` key yet, one is appended at the end of the file.
    """
    lines = text.splitlines(keepends=True)
    found = _find_block(lines, 0, len(lines), "", "profiles:")
    if found is None:
        sep = "" if not text or text.endswith("\n") else "\n"
        return text + sep + "profiles:\n" + indented_block

    _, end = found
    return "".join(lines[:end] + [indented_block] + lines[end:])


def _replace_profile_block(text: str, name: str, indented_block: str) -> str:
    """Replace only the `name:` profile's own block under `profiles:`.

    Pure text splice, like `_splice_under_profiles` — the rest of the file
    (other profiles, comments, unrelated config) is left byte-for-byte as-is.
    """
    lines = text.splitlines(keepends=True)
    profiles_found = _find_block(lines, 0, len(lines), "", "profiles:")
    if profiles_found is None:
        raise ProfileNameExistsError("No 'profiles:' section found in the file to update.")
    p_start, p_end = profiles_found

    name_found = _find_block(lines, p_start + 1, p_end, "  ", f"{name}:")
    if name_found is None:
        raise ProfileNameExistsError(f"Profile '{name}' not found under 'profiles:'.")
    n_start, n_end = name_found
    return "".join(lines[:n_start] + [indented_block] + lines[n_end:])


def _write_profile(path: Path, name: str, draft: ProfileDraft, *, force: bool) -> None:
    text = path.read_text() if path.exists() else ""
    data = (yaml.safe_load(text) or {}) if text.strip() else {}
    existing = (data.get("profiles") or {}).get(name)
    exists = existing is not None
    if exists and not force:
        raise ProfileNameExistsError(
            f"Profile '{name}' already exists in {path}. Use --force to overwrite."
        )

    if exists:
        # Re-draft titles/skills/keywords, but keep any hard-filter setting the
        # profile already has — only fill in the ones it doesn't have yet.
        fields = profile_fields(draft)
        for key in DEFAULT_PROFILE_SETTINGS:
            if key in existing:
                fields[key] = existing[key]
        block = to_yaml_block_from_fields(name, fields)
    else:
        block = to_yaml_block(name, draft)

    indented = "".join(
        ("  " + line if line.strip() else line)
        for line in block.splitlines(keepends=True)
    )

    if exists:
        # Overwrite only this profile's own block — everything else in the
        # file (other profiles, comments, unrelated config) is untouched.
        path.write_text(_replace_profile_block(text, name, indented))
        return

    path.write_text(_splice_under_profiles(text, indented))


def run_from_resume(
    config: Config,
    name: str,
    resume: str | Path,
    *,
    config_path: str | Path | None = None,
    write: bool = False,
    force: bool = False,
    model: str | None = None,
    on_info: Callable[[str], None] = _noop,
    on_llm_log: Callable[[str], None] | None = None,
) -> FromResumeResult:
    """Draft a Profile named `name` from the resume at `resume`.

    Default behavior only drafts (the YAML block is returned for the CLI to
    print); `write=True` persists it under `<name>` in `config_path`, refusing a
    name collision unless `force=True`. `--force` replaces only that profile's
    own block — the rest of the file (other profiles, comments, unrelated
    config) is left untouched. Raises a `CommandError` subclass instead of
    exiting when the resume file or LLM provider is unavailable.

    Every LLM call is logged: the request/response stream through `on_llm_log`
    (``None`` to silence it) and a token/cost summary is always emitted through
    `on_info`, the same observability contract as `report --enrich`.
    """
    resume_text = _load_resume_text(resume)

    provider = build_provider(config.llm.provider, api_key=config.llm.api_key)
    if provider is None:
        raise LLMUnavailableError(
            "LLM unavailable — install it with: pip install -e '.[llm]' and set "
            "llm.api_key in config (or ANTHROPIC_API_KEY)"
        )

    used_model = model or config.llm.draft_model
    draft, comp = draft_profile(provider, used_model, resume_text, logger=on_llm_log)
    usage = Usage(model=used_model)
    usage.add(comp)
    on_info(format_usage(usage, config.llm, label="LLM profile-draft usage"))

    block = to_yaml_block(name, draft)

    written_to = None
    if write:
        path = Path(config_path or "config.yaml")
        _write_profile(path, name, draft, force=force)
        written_to = path

    return FromResumeResult(name=name, draft=draft, yaml_block=block, written_to=written_to)
