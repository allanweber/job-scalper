"""Auth endpoints: Google sign-in, token refresh, logout (ADR 0010)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from scalper.service.auth import AccountInactive, AuthError, InvalidToken
from scalper.service.deps import RequestContext, get_ctx
from scalper.service.routers._helpers import token_response, user_response
from scalper.service.schemas import (
    GoogleSignInRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    SignInResponse,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=SignInResponse)
def sign_in_google(body: GoogleSignInRequest, ctx: RequestContext = Depends(get_ctx)):
    auth = ctx.container.auth_service(ctx.conn)
    try:
        user, tokens = auth.sign_in_with_google(body.id_token, device_info=body.device_info)
    except AccountInactive as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from e
    except (InvalidToken, AuthError) as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    return SignInResponse(user=user_response(user), tokens=token_response(tokens))


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, ctx: RequestContext = Depends(get_ctx)):
    auth = ctx.container.auth_service(ctx.conn)
    try:
        _user, tokens = auth.refresh(body.refresh_token, device_info=body.device_info)
    except AccountInactive as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from e
    except InvalidToken as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    return token_response(tokens)


@router.post("/logout", response_model=MessageResponse)
def logout(body: LogoutRequest, ctx: RequestContext = Depends(get_ctx)):
    ctx.container.auth_service(ctx.conn).logout(body.refresh_token)
    return MessageResponse(message="logged out")
