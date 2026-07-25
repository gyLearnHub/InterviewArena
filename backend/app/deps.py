from collections.abc import Iterator
from secrets import compare_digest

from fastapi import Depends, Header, Request, status

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.origins import is_origin_allowed, request_source_origin
from app.core.security import decode_access_token
from app.db.mysql import mysql_connection
from app.repositories.users import UserRecord, UserRepository


def get_user_repository() -> Iterator[UserRepository]:
    with mysql_connection() as connection:
        yield UserRepository(connection)


UserRepositoryDep = Depends(get_user_repository)


def get_authenticated_user_id(
    request: Request = None,  # type: ignore[assignment]
    authorization: str | None = Header(default=None),
) -> int:
    settings = get_settings()
    auth_cookie = request.cookies.get(settings.auth_cookie_name) if request is not None else None
    token = auth_cookie or _extract_bearer_token(authorization)
    if auth_cookie is not None:
        _validate_csrf_token(request)
    payload = decode_access_token(token)
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise AppError(ErrorCode.UNAUTHORIZED, status.HTTP_401_UNAUTHORIZED)
    return int(subject)


AuthenticatedUserIdDep = Depends(get_authenticated_user_id)


def get_current_user(
    user_id: int = AuthenticatedUserIdDep,
    users: UserRepository = UserRepositoryDep,
) -> UserRecord:
    user = users.get_by_id(user_id)

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


def _validate_csrf_token(request: Request | None) -> None:
    if request is None or request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    settings = get_settings()
    if not settings.csrf_protection_enabled or settings.app_env.strip().lower() in {
        "test",
        "testing",
        "pytest",
    }:
        return
    source_origin = request_source_origin(
        request.headers.get("origin"),
        request.headers.get("referer"),
    )
    if source_origin is not None and not is_origin_allowed(source_origin, settings):
        raise AppError(
            ErrorCode.FORBIDDEN,
            status.HTTP_403_FORBIDDEN,
            message="请求来源不受信任。",
        )
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get(settings.csrf_header_name)
    if (
        not cookie_token
        or not header_token
        or not compare_digest(cookie_token, header_token)
    ):
        raise AppError(ErrorCode.FORBIDDEN, status.HTTP_403_FORBIDDEN, message="CSRF 校验失败。")
