import secrets
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
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
REGISTRATION_ATTEMPT_LIMIT = 10
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
    http_request: Request = None,  # type: ignore[assignment]
    users: UserRepository = UserRepositoryDep,
) -> UserPublic:
    username = request.username.strip()
    password = request.password
    if not username or not password:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
    _enforce_registration_rate_limit(http_request, users)
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
    password = request.password
    source_ip = _source_ip_from_request(http_request)
    _ensure_login_not_limited(username, source_ip, users)
    user = users.get_by_username(username)
    if user is None or not verify_password(password, user.password_hash):
        _record_login_failure(username, source_ip, users)
        raise AppError(
            ErrorCode.UNAUTHORIZED,
            status.HTTP_401_UNAUTHORIZED,
            message="用户名或密码错误。",
        )

    _clear_login_failures(username, source_ip, users)
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
    try:
        users.commit()
    except Exception:
        with suppress(OSError):
            avatar_path.unlink()
        raise
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


def _enforce_registration_rate_limit(
    request: Request | None,
    users: UserRepository,
) -> None:
    consume = getattr(users, "consume_auth_rate_limit", None)
    if request is None or not callable(consume):
        return
    source_ip = _source_ip_from_request(request)
    identifier_hash = sha256(source_ip.encode("utf-8")).hexdigest()
    window_started_at = datetime.now(UTC).replace(
        minute=0,
        second=0,
        microsecond=0,
        tzinfo=None,
    )
    if not consume(
        scope="registration_ip",
        identifier_hash=identifier_hash,
        window_started_at=window_started_at,
        limit=REGISTRATION_ATTEMPT_LIMIT,
    ):
        users.commit()
        raise AppError(
            ErrorCode.TOO_MANY_REQUESTS,
            status.HTTP_429_TOO_MANY_REQUESTS,
            message="注册请求过于频繁，请稍后再试。",
        )
    users.commit()


def _login_failure_key(username: str, source_ip: str) -> str:
    return f"{username.strip().casefold()}|{source_ip.strip() or 'unknown'}"


def _now() -> float:
    return monotonic()


def _ensure_login_not_limited(
    username: str,
    source_ip: str,
    users: UserRepository,
) -> None:
    if not username.strip():
        return
    get_count = getattr(users, "get_auth_rate_limit_count", None)
    if callable(get_count):
        if (
            get_count(
                scope="login_failure",
                identifier_hash=_login_failure_hash(username, source_ip),
                window_started_at=_login_failure_window(),
            )
            >= LOGIN_FAILURE_LIMIT
        ):
            raise AppError(
                ErrorCode.TOO_MANY_REQUESTS,
                status.HTTP_429_TOO_MANY_REQUESTS,
                message="登录失败次数过多，请稍后再试。",
            )
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


def _record_login_failure(
    username: str,
    source_ip: str,
    users: UserRepository | None = None,
) -> None:
    if not username.strip():
        return
    consume = getattr(users, "consume_auth_rate_limit", None)
    if users is not None and callable(consume):
        consume(
            scope="login_failure",
            identifier_hash=_login_failure_hash(username, source_ip),
            window_started_at=_login_failure_window(),
            limit=LOGIN_FAILURE_LIMIT,
        )
        users.commit()
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


def _clear_login_failures(
    username: str,
    source_ip: str,
    users: UserRepository,
) -> None:
    clear = getattr(users, "clear_auth_rate_limit", None)
    if callable(clear):
        clear(
            scope="login_failure",
            identifier_hash=_login_failure_hash(username, source_ip),
        )
        return
    with _login_failures_lock:
        _login_failures.pop(_login_failure_key(username, source_ip), None)


def _login_failure_hash(username: str, source_ip: str) -> str:
    key = _login_failure_key(username, source_ip)
    return sha256(key.encode("utf-8")).hexdigest()


def _login_failure_window() -> datetime:
    now = datetime.now(UTC)
    window_minute = now.minute - (now.minute % max(1, LOGIN_FAILURE_WINDOW_SECONDS // 60))
    return now.replace(
        minute=window_minute,
        second=0,
        microsecond=0,
        tzinfo=None,
    )


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
