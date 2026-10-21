"""Account registration and browser-session endpoints."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.config import get_settings
from app.core.security import (
    SESSION_COOKIE_NAME,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)
from app.infrastructure.models.auth import AuthSessionRecord, UserRecord
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut


router = APIRouter(prefix="/auth")


def _error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.auth_session_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.app_env.lower() in {"production", "prod"},
        samesite="lax",
        path="/",
    )


def _create_session(db: Session, user: UserRecord) -> str:
    now = datetime.now(timezone.utc)
    token = new_session_token()
    db.add(AuthSessionRecord(
        id=uuid4().hex,
        user_id=user.id,
        token_hash=hash_session_token(token),
        created_at=now,
        expires_at=now + timedelta(days=get_settings().auth_session_days),
    ))
    return token


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    existing = db.scalar(select(UserRecord).where(UserRecord.email == payload.email))
    if existing is not None:
        raise _error("email_already_registered", "该邮箱已注册", status.HTTP_409_CONFLICT)
    user = UserRecord(
        id=uuid4().hex,
        email=payload.email,
        password_hash=hash_password(payload.password),
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    token = _create_session(db, user)
    db.commit()
    db.refresh(user)
    _set_session_cookie(response, token)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(UserRecord).where(UserRecord.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise _error("invalid_credentials", "邮箱或密码错误", status.HTTP_401_UNAUTHORIZED)
    token = _create_session(db, user)
    db.commit()
    _set_session_cookie(response, token)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
):
    if session_token:
        record = db.scalar(select(AuthSessionRecord).where(
            AuthSessionRecord.token_hash == hash_session_token(session_token),
            AuthSessionRecord.revoked_at.is_(None),
        ))
        if record is not None:
            record.revoked_at = datetime.now(timezone.utc)
            db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
def me(user: UserRecord = Depends(get_current_user)):
    return user
