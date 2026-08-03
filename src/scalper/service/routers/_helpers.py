"""Shared mapping helpers between internal records and API schemas."""

from __future__ import annotations

from scalper.service.content_repos import JobRecord, StoredProfile
from scalper.service.models import TokenPair, User
from scalper.service.schemas import (
    JobResponse,
    ProfileResponse,
    TokenResponse,
    UserResponse,
)


def user_response(user: User, *, has_profile: bool = False) -> UserResponse:
    return UserResponse(
        id=user.id, email=user.email, display_name=user.display_name,
        avatar_url=user.avatar_url, role=user.role, plan=user.plan,
        tos_accepted=user.tos_accepted_at is not None,
        privacy_accepted=user.privacy_accepted_at is not None,
        has_profile=has_profile,
    )


def token_response(pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token,
        token_type=pair.token_type, expires_in=pair.expires_in,
    )


def profile_response(p: StoredProfile) -> ProfileResponse:
    return ProfileResponse(
        id=p.id, name=p.name, titles=p.titles, required_skills=p.required_skills,
        nice_to_have_skills=p.nice_to_have_skills, keywords=p.keywords,
        exclude_keywords=p.exclude_keywords, remote_only=p.remote_only,
        salary_floor=p.salary_floor, exclude_non_latin=p.exclude_non_latin,
        origin=p.origin,
    )


def job_response(j: JobRecord) -> JobResponse:
    return JobResponse(
        id=j.id, kind=j.kind, status=j.status, result=j.result, error=j.error,
        created_at=j.created_at, finished_at=j.finished_at,
    )
