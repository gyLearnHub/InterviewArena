import secrets
from contextlib import suppress
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Literal, cast

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.http_status import (
    HTTP_413_CONTENT_TOO_LARGE,
    HTTP_422_UNPROCESSABLE_CONTENT,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.deps import get_current_user, get_user_repository
from app.repositories.users import DuplicateUsernameError, UserRecord, UserRepository
from app.schemas.auth import AuthRequest, LoginResponse, UserProfileUpdate, UserPublic
from app.services.avatar_storage import (
    MAX_AVATAR_BYTES,
    avatar_public_url,
    delete_avatar_by_public_url,
    make_avatar_path,
    resolve_avatar_upload_dir,
    validate_avatar_upload,
)

router = APIRouter(prefix="/auth", tags=["auth"])
UserRepositoryDep = Depends(get_user_repository)
CurrentUserDep = Depends(get_current_user)
AvatarFile = File(...)
LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW_SECONDS = 300
LOGIN_LOCK_SECONDS = 300
LOGIN_FAILURE_MAX_ENTRIES = 4096
CookieSameSite = Literal["lax", "strict", "none"]


@dataclass
class LoginFailureState:
    count: int
    first_failed_at: float
    locked_until: float | None = None


_login_failures: dict[str, LoginFailureState] = {}
_login_failures_lock = Lock()


@router.post("/register", response_model=UserPublic)
def register(
    request: AuthRequest,
    users: UserRepository = UserRepositoryDep,
) -> UserPublic:
    username = request.username.strip()
    password = request.password.strip()
    if not username or not password:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
    if users.get_by_username(username) is not None:
        raise AppError(
            ErrorCode.CONFLICT,
            status.HTTP_409_CONFLICT,
            message="用户名已存在。",
        )

    try:
        user = users.create(username=username, password_hash=hash_password(password))
    except DuplicateUsernameError as exc:
        raise AppError(
            ErrorCode.CONFLICT,
            status.HTTP_409_CONFLICT,
            message="用户名已存在。",
        ) from exc
    return _to_user_public(user)


@router.post("/login", response_model=LoginResponse)
def login(
    request: AuthRequest,
    http_request: Request,
    response: Response = None,  # type: ignore[assignment]
    users: UserRepository = UserRepositoryDep,
) -> LoginResponse:
    username = request.username.strip()
    password = request.password.strip()
    source_ip = _source_ip_from_request(http_request)
    _ensure_login_not_limited(username, source_ip)
    user = users.get_by_username(username)
    if user is None or not verify_password(password, user.password_hash):
        _record_login_failure(username, source_ip)
        raise AppError(
            ErrorCode.UNAUTHORIZED,
            status.HTTP_401_UNAUTHORIZED,
            message="用户名或密码错误。",
        )

    _clear_login_failures(username, source_ip)
    access_token = create_access_token(user.id)
    if response is not None:
        _set_auth_cookie(response, access_token)
        _set_csrf_cookie(response)
    return LoginResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name or user.username,
        avatar_url=user.avatar_url,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=_cookie_samesite(settings.auth_cookie_samesite),
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=False,
        samesite=_cookie_samesite(settings.auth_cookie_samesite),
    )


@router.get("/me", response_model=UserPublic)
def read_current_user(current_user: UserRecord = CurrentUserDep) -> UserPublic:
    return _to_user_public(current_user)


@router.patch("/me", response_model=UserPublic)
def update_current_user(
    request: UserProfileUpdate,
    current_user: UserRecord = CurrentUserDep,
    users: UserRepository = UserRepositoryDep,
) -> UserPublic:
    display_name = request.display_name.strip()
    if not display_name:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
    user = users.update_display_name(current_user.id, display_name)
    if user is None:
        raise AppError(ErrorCode.UNAUTHORIZED, status.HTTP_401_UNAUTHORIZED)
    return _to_user_public(user)


@router.post("/me/avatar", response_model=UserPublic)
async def upload_current_user_avatar(
    file: UploadFile = AvatarFile,
    current_user: UserRecord = CurrentUserDep,
    users: UserRepository = UserRepositoryDep,
) -> UserPublic:
    content = await file.read(MAX_AVATAR_BYTES + 1)
    if len(content) > MAX_AVATAR_BYTES:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_413_CONTENT_TOO_LARGE)

    extension = validate_avatar_upload(file.filename or "", file.content_type, content)
    upload_dir = resolve_avatar_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    avatar_path = make_avatar_path(current_user.id, extension, upload_dir)
    avatar_path.write_bytes(content)

    existing_user = users.get_by_id(current_user.id)
    old_avatar_url = (
        existing_user.avatar_url if existing_user is not None else current_user.avatar_url
    )
    user = users.update_avatar_url(current_user.id, avatar_public_url(avatar_path))
    if user is None:
        with suppress(OSError):
            avatar_path.unlink()
        raise AppError(ErrorCode.UNAUTHORIZED, status.HTTP_401_UNAUTHORIZED)
    delete_avatar_by_public_url(old_avatar_url, upload_dir, keep_url=user.avatar_url)
    return _to_user_public(user)


def _to_user_public(user: UserRecord) -> UserPublic:
    return UserPublic(
        id=user.id,
        username=user.username,
        display_name=user.display_name or user.username,
        avatar_url=user.avatar_url,
    )


def _set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=max(settings.jwt_expire_minutes * 60, 0),
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite=_cookie_samesite(settings.auth_cookie_samesite),
    )


def _set_csrf_cookie(response: Response) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=secrets.token_urlsafe(32),
        max_age=max(settings.jwt_expire_minutes * 60, 0),
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=False,
        samesite=_cookie_samesite(settings.auth_cookie_samesite),
    )


def _cookie_samesite(value: str) -> CookieSameSite:
    normalized = value.strip().lower()
    if normalized not in {"lax", "strict", "none"}:
        return "lax"
    return cast(CookieSameSite, normalized)


def _source_ip_from_request(request: Request) -> str:
    if request.client is None or not request.client.host:
        return "unknown"
    return request.client.host


def _login_failure_key(username: str, source_ip: str) -> str:
    return f"{username.strip().casefold()}|{source_ip.strip() or 'unknown'}"


def _now() -> float:
    return monotonic()


def _ensure_login_not_limited(username: str, source_ip: str) -> None:
    if not username.strip():
        return
    key = _login_failure_key(username, source_ip)
    now = _now()
    with _login_failures_lock:
        state = _login_failures.get(key)
        if state is None:
            return
        if state.locked_until is not None:
            if state.locked_until > now:
                raise AppError(
                    ErrorCode.TOO_MANY_REQUESTS,
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    message="登录失败次数过多，请稍后再试。",
                )
            _login_failures.pop(key, None)
            return
        if now - state.first_failed_at > LOGIN_FAILURE_WINDOW_SECONDS:
            _login_failures.pop(key, None)


def _record_login_failure(username: str, source_ip: str) -> None:
    if not username.strip():
        return
    key = _login_failure_key(username, source_ip)
    now = _now()
    with _login_failures_lock:
        _prune_login_failures(now)
        state = _login_failures.get(key)
        if state is None or now - state.first_failed_at > LOGIN_FAILURE_WINDOW_SECONDS:
            _login_failures[key] = LoginFailureState(count=1, first_failed_at=now)
            _enforce_login_failure_capacity()
            return
        state.count += 1
        if state.count >= LOGIN_FAILURE_LIMIT:
            state.locked_until = now + LOGIN_LOCK_SECONDS


def _clear_login_failures(username: str, source_ip: str) -> None:
    with _login_failures_lock:
        _login_failures.pop(_login_failure_key(username, source_ip), None)


def _prune_login_failures(now: float) -> None:
    expired_keys = [
        key
        for key, state in _login_failures.items()
        if (
            state.locked_until is not None
            and state.locked_until <= now
        )
        or (
            state.locked_until is None
            and now - state.first_failed_at > LOGIN_FAILURE_WINDOW_SECONDS
        )
    ]
    for key in expired_keys:
        _login_failures.pop(key, None)


def _enforce_login_failure_capacity() -> None:
    while len(_login_failures) > LOGIN_FAILURE_MAX_ENTRIES:
        oldest_key = min(
            _login_failures,
            key=lambda key: _login_failures[key].first_failed_at,
        )
        _login_failures.pop(oldest_key, None)
