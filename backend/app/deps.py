from collections.abc import Iterator

from fastapi import Depends, Header, Request, status

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.security import decode_access_token
from app.db.mysql import mysql_connection
from app.repositories.users import UserRecord, UserRepository


def get_user_repository() -> Iterator[UserRepository]:
    with mysql_connection() as connection:
        yield UserRepository(connection)


UserRepositoryDep = Depends(get_user_repository)


def get_current_user(
    request: Request = None,  # type: ignore[assignment]
    authorization: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    users: UserRepository = UserRepositoryDep,
) -> UserRecord:
    settings = get_settings()
    auth_cookie = request.cookies.get(settings.auth_cookie_name) if request is not None else None
    token = auth_cookie or _extract_bearer_token(authorization)
    if auth_cookie is not None:
        _validate_csrf_token(request, x_csrf_token)
    payload = decode_access_token(token)
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise AppError(ErrorCode.UNAUTHORIZED, status.HTTP_401_UNAUTHORIZED)

    user = users.get_by_id(int(subject))
    if user is None:
        raise AppError(ErrorCode.UNAUTHORIZED, status.HTTP_401_UNAUTHORIZED)
    return user


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise AppError(ErrorCode.UNAUTHORIZED, status.HTTP_401_UNAUTHORIZED)
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AppError(ErrorCode.UNAUTHORIZED, status.HTTP_401_UNAUTHORIZED)
    return token


def _validate_csrf_token(request: Request | None, header_token: str | None) -> None:
    if request is None or request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    settings = get_settings()
    if not settings.csrf_protection_enabled or settings.app_env.strip().lower() in {
        "test",
        "testing",
        "pytest",
    }:
        return
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    if not cookie_token or not header_token or cookie_token != header_token:
        raise AppError(ErrorCode.FORBIDDEN, status.HTTP_403_FORBIDDEN, message="CSRF 校验失败。")
