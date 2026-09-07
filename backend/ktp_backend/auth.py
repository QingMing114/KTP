from __future__ import annotations

import hashlib
import logging
import os
import re
import time

import jwt
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from v2.runtime.user_store import UserStore
from schemas.runtime import AuthTokenPayload, PublicUserRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/auth", tags=["auth"])

_JWT_SECRET = os.environ.get("APP_JWT_SECRET", "")
_DEFAULT_SECRET_WARNING = "ktp-stable-jwt-secret-2024-a7f3b9c1e5d2"
if not _JWT_SECRET or _JWT_SECRET == _DEFAULT_SECRET_WARNING:
    _JWT_SECRET = hashlib.sha256(os.urandom(32)).hexdigest()
    logger.warning(
        "APP_JWT_SECRET not set or using default value. "
        "Generated random secret — tokens will be invalid after restart. "
        "Set APP_JWT_SECRET in .env for production use."
    )

_JWT_TTL_SECONDS = 86400 * 7

_USER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,32}$")


class AuthLoginRequest(BaseModel):
    user_id: str = Field(min_length=2, max_length=32, description="User ID")
    password: str = Field(min_length=4, max_length=128, description="Password")


class AuthRegisterRequest(BaseModel):
    user_id: str = Field(min_length=2, max_length=32, description="User ID")
    password: str = Field(min_length=4, max_length=128, description="Password")


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=4, max_length=128)
    new_password: str = Field(min_length=4, max_length=128)


def _validate_user_id(user_id: str) -> None:
    if not _USER_ID_PATTERN.match(user_id):
        raise HTTPException(
            status_code=422,
            detail="user_id must be 2-32 chars, only letters, digits, underscore, hyphen",
        )


def _encode_jwt(payload: AuthTokenPayload) -> str:
    return jwt.encode(payload.model_dump(), _JWT_SECRET, algorithm="HS256")


def decode_jwt(token: str) -> AuthTokenPayload:
    try:
        data = jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("JWT expired") from exc
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"Invalid JWT: {exc}") from exc
    return AuthTokenPayload.model_validate(data)


def _require_auth(authorization: str) -> AuthTokenPayload:
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        return decode_jwt(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


_user_store: UserStore | None = None


def get_user_store() -> UserStore:
    global _user_store
    if _user_store is None:
        _user_store = UserStore()
    return _user_store


def set_user_store(store: UserStore) -> None:
    global _user_store
    _user_store = store


def _to_public(user) -> PublicUserRecord:
    return PublicUserRecord(
        user_id=user.user_id,
        role=user.role,
        created_at=user.created_at,
        last_login=user.last_login,
    )


@router.post("/register")
def register(body: AuthRegisterRequest) -> dict:
    _validate_user_id(body.user_id)
    store = get_user_store()
    is_first_user = store.count_users() == 0
    role = "admin" if is_first_user else "user"
    try:
        user = store.create_user(body.user_id, body.password, role=role)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    payload = AuthTokenPayload(user_id=user.user_id, role=user.role, exp=time.time() + _JWT_TTL_SECONDS)
    token = _encode_jwt(payload)
    return {"user_id": user.user_id, "role": user.role, "access_token": token}


@router.post("/login")
def login(body: AuthLoginRequest) -> dict:
    _validate_user_id(body.user_id)
    store = get_user_store()
    if not store.verify_password(body.user_id, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = store.get_user(body.user_id)
    if user is None:
        raise HTTPException(status_code=500, detail="User found but get failed")
    store.update_last_login(body.user_id)
    payload = AuthTokenPayload(user_id=user.user_id, role=user.role, exp=time.time() + _JWT_TTL_SECONDS)
    token = _encode_jwt(payload)
    return {"user_id": user.user_id, "role": user.role, "access_token": token}


@router.get("/me")
def get_me(authorization: str = Header(default="")) -> dict:
    payload = _require_auth(authorization)
    store = get_user_store()
    user = store.get_user(payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user.user_id, "role": user.role, "created_at": user.created_at, "last_login": user.last_login}


@router.post("/logout")
def logout(authorization: str = Header(default="")) -> dict:
    _require_auth(authorization)
    return {"status": "ok", "detail": "Token invalidated on client side"}


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, authorization: str = Header(default="")) -> dict:
    payload = _require_auth(authorization)
    store = get_user_store()
    if not store.verify_password(payload.user_id, body.old_password):
        raise HTTPException(status_code=401, detail="Old password is incorrect")
    store.update_password(payload.user_id, body.new_password)
    return {"status": "ok", "detail": "Password changed successfully"}


@router.get("/users", response_model=list[PublicUserRecord])
def list_users(authorization: str = Header(default="")) -> list[PublicUserRecord]:
    payload = _require_auth(authorization)
    if payload.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    store = get_user_store()
    return [_to_public(u) for u in store.list_users()]
