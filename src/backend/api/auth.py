from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr

from backend.deps import Dependencies, get_current_user_id, get_deps
from backend.security.jwt_tokens import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    captcha_token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class HFCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


def _token_for(user_id: str, deps: Dependencies) -> TokenOut:
    return TokenOut(access_token=create_access_token(user_id, deps.settings.jwt_secret))


@router.post("/register", response_model=TokenOut)
def register(body: RegisterRequest, deps: Dependencies = Depends(get_deps)) -> TokenOut:
    user = deps.auth_service.register_with_email(body.email, body.password, body.captcha_token)
    return _token_for(user.id, deps)


@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest, deps: Dependencies = Depends(get_deps)) -> TokenOut:
    user = deps.auth_service.login_with_email(body.email, body.password)
    return _token_for(user.id, deps)


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    deps: Dependencies = Depends(get_deps),
    user_id: str = Depends(get_current_user_id),
) -> None:
    deps.auth_service.change_password(user_id, body.old_password, body.new_password)


@router.post("/hf/callback", response_model=TokenOut)
def hf_oauth_callback(body: HFCallbackRequest, deps: Dependencies = Depends(get_deps)) -> TokenOut:
    user = deps.auth_service.login_or_register_with_hf(body.code, body.redirect_uri)
    return _token_for(user.id, deps)
