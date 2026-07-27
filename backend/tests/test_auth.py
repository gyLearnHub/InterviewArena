
import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import app.api.auth as auth_module
import app.deps as deps_module
import pytest
from app.api.auth import (
    delete_current_user_account,
    login,
    read_current_user,
    register,
    update_current_user,
    upload_current_user_avatar,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode
from app.core.security import create_access_token, hash_password
from app.deps import get_current_user, get_user_repository
from app.repositories.users import DuplicateUsernameError, UserRecord
from app.schemas.auth import (
    AccountDeleteRequest,
    AuthRequest,
    RegisterRequest,
    UserProfileUpdate,
)
from fastapi import Response, UploadFile
from fastapi.testclient import TestClient
from main import create_app
from pydantic import ValidationError
from starlette.datastructures import Headers
from starlette.requests import Request


class FakeUserRepository:
    def __init__(self) -> None:
        self.users_by_id: dict[int, UserRecord] = {}
        self.users_by_username: dict[str, UserRecord] = {}
        self.next_id = 1
        self.commit_error: Exception | None = None

    def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error

    def get_by_id(self, user_id: int) -> UserRecord | None:
        return self.users_by_id.get(user_id)

    def get_by_username(self, username: str) -> UserRecord | None:
        return self.users_by_username.get(username)

    def create(self, username: str, password_hash: str) -> UserRecord:
        user = UserRecord(
            id=self.next_id,
            username=username,
            display_name=username,
            password_hash=password_hash,
            external_model_consent=False,
        )
        self.next_id += 1
        self.users_by_id[user.id] = user
        self.users_by_username[user.username] = user
        return user

    def update_display_name(self, user_id: int, display_name: str) -> UserRecord | None:
        user = self.users_by_id.get(user_id)
        if user is None:
            return None
        updated = UserRecord(
            id=user.id,
            username=user.username,
            display_name=display_name,
            avatar_url=user.avatar_url,
            password_hash=user.password_hash,
            memory_enabled=user.memory_enabled,
            memory_updated_at=user.memory_updated_at,
            external_model_consent=user.external_model_consent,
        )
        self.users_by_id[user_id] = updated
        self.users_by_username[updated.username] = updated
        return updated

    def update_avatar_url(self, user_id: int, avatar_url: str) -> UserRecord | None:
        user = self.users_by_id.get(user_id)
        if user is None:
            return None
        updated = UserRecord(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            avatar_url=avatar_url,
            password_hash=user.password_hash,
            memory_enabled=user.memory_enabled,
            memory_updated_at=user.memory_updated_at,
            external_model_consent=user.external_model_consent,
        )
        self.users_by_id[user_id] = updated
        self.users_by_username[updated.username] = updated
        return updated

    def update_external_model_consent(
        self,
        user_id: int,
        consent: bool,
    ) -> UserRecord | None:
        user = self.users_by_id.get(user_id)
        if user is None:
            return None
        updated = UserRecord(
            **{
                **user.__dict__,
                "external_model_consent": consent,
            }
        )
        self.users_by_id[user_id] = updated
        self.users_by_username[updated.username] = updated
        return updated


def request_from_ip(source_ip: str = "127.0.0.1") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": [],
            "client": (source_ip, 54321),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def test_register_success() -> None:
    repository = FakeUserRepository()

    response = register(
        AuthRequest(username="alice", password="secret"),
        users=repository,  # type: ignore[arg-type]
    )

    assert response.model_dump() == {
        "id": 1,
        "username": "alice",
        "display_name": "alice",
        "avatar_url": None,
        "external_model_consent": False,
    }
    user = repository.get_by_username("alice")
    assert user is not None
    assert user.password_hash != "secret"


def test_register_can_record_explicit_external_model_consent() -> None:
    repository = FakeUserRepository()

    response = register(
        RegisterRequest(
            username="alice",
            password="secret",
            external_model_consent=True,
        ),
        users=repository,  # type: ignore[arg-type]
    )

    assert response.external_model_consent is True
    assert repository.get_by_username("alice").external_model_consent is True  # type: ignore[union-attr]


def test_auth_request_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        AuthRequest(username="alice", password="1")


def test_register_duplicate_username() -> None:
    repository = FakeUserRepository()
    repository.create("alice", hash_password("secret"))

    with pytest.raises(AppError) as error_info:
        register(
            AuthRequest(username="alice", password="another-secret"),
            users=repository,  # type: ignore[arg-type]
        )

    assert error_info.value.status_code == 409
    assert error_info.value.code == ErrorCode.CONFLICT
    assert error_info.value.message == "用户名已存在。"


def test_register_duplicate_username_from_database_race_returns_conflict() -> None:
    class RacingRepository(FakeUserRepository):
        def create(self, username: str, password_hash: str) -> UserRecord:
            raise DuplicateUsernameError(username)

    with pytest.raises(AppError) as error_info:
        register(
            AuthRequest(username="alice", password="secret"),
            users=RacingRepository(),  # type: ignore[arg-type]
        )

    assert error_info.value.status_code == 409
    assert error_info.value.code == ErrorCode.CONFLICT
    assert error_info.value.message == "用户名已存在。"


def test_login_wrong_password() -> None:
    repository = FakeUserRepository()
    repository.create("alice", hash_password("secret"))

    with pytest.raises(AppError) as error_info:
        login(
            AuthRequest(username="alice", password="wrong-password"),
            request_from_ip(),
            users=repository,  # type: ignore[arg-type]
        )

    assert error_info.value.status_code == 401
    assert error_info.value.code == ErrorCode.UNAUTHORIZED
    assert error_info.value.message == "用户名或密码错误。"


def test_login_is_temporarily_limited_after_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeUserRepository()
    repository.create("alice", hash_password("secret"))
    now = 1_000.0
    monkeypatch.setattr(auth_module, "_now", lambda: now)
    auth_module._login_failures.clear()

    for _ in range(auth_module.LOGIN_FAILURE_LIMIT):
        with pytest.raises(AppError) as error_info:
            login(
                AuthRequest(username="alice", password="wrong-password"),
                request_from_ip(),
                users=repository,  # type: ignore[arg-type]
            )
        assert error_info.value.status_code == 401

    with pytest.raises(AppError) as error_info:
        login(
            AuthRequest(username="alice", password="secret"),
            request_from_ip(),
            users=repository,  # type: ignore[arg-type]
        )

    assert error_info.value.status_code == 429
    assert error_info.value.code == ErrorCode.TOO_MANY_REQUESTS

    now += auth_module.LOGIN_LOCK_SECONDS + 1
    response = login(
        AuthRequest(username="alice", password="secret"),
        request_from_ip(),
        users=repository,  # type: ignore[arg-type]
    )

    assert response.username == "alice"
    assert auth_module._login_failures == {}


def test_login_limit_is_scoped_by_username_and_source_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeUserRepository()
    repository.create("alice", hash_password("secret"))
    monkeypatch.setattr(auth_module, "_now", lambda: 1_500.0)
    auth_module._login_failures.clear()

    for _ in range(auth_module.LOGIN_FAILURE_LIMIT):
        with pytest.raises(AppError):
            login(
                AuthRequest(username="alice", password="wrong-password"),
                request_from_ip("10.0.0.1"),
                users=repository,  # type: ignore[arg-type]
            )

    response = login(
        AuthRequest(username="alice", password="secret"),
        request_from_ip("10.0.0.2"),
        users=repository,  # type: ignore[arg-type]
    )

    assert response.username == "alice"
    assert "alice|10.0.0.1" in auth_module._login_failures
    assert "alice|10.0.0.2" not in auth_module._login_failures


def test_login_success_clears_previous_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeUserRepository()
    repository.create("alice", hash_password("secret"))
    monkeypatch.setattr(auth_module, "_now", lambda: 2_000.0)
    auth_module._login_failures.clear()

    with pytest.raises(AppError):
        login(
            AuthRequest(username="alice", password="wrong-password"),
            request_from_ip(),
            users=repository,  # type: ignore[arg-type]
        )

    login(
        AuthRequest(username="alice", password="secret"),
        request_from_ip(),
        users=repository,  # type: ignore[arg-type]
    )

    assert auth_module._login_failures == {}


def test_login_failure_store_prunes_expired_entries_and_caps_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeUserRepository()
    now = 10_000.0
    monkeypatch.setattr(auth_module, "_now", lambda: now)
    monkeypatch.setattr(auth_module, "LOGIN_FAILURE_MAX_ENTRIES", 3)
    auth_module._login_failures.clear()
    auth_module._login_failures["expired|10.0.0.1"] = auth_module.LoginFailureState(
        count=1,
        first_failed_at=now - auth_module.LOGIN_FAILURE_WINDOW_SECONDS - 1,
    )

    for index in range(6):
        auth_module._reserve_login_attempt(
            f"random-{index}",
            f"10.0.0.{index}",
            repository,  # type: ignore[arg-type]
        )

    assert "expired|10.0.0.1" not in auth_module._login_failures
    assert len(auth_module._login_failures) <= 3


def test_login_attempt_reservation_is_atomic_for_concurrent_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeUserRepository()
    repository.create("alice", hash_password("secret"))
    monkeypatch.setattr(auth_module, "_now", lambda: 12_000.0)
    auth_module._login_failures.clear()

    def attempt() -> int:
        try:
            login(
                AuthRequest(username="alice", password="wrong-password"),
                request_from_ip(),
                users=repository,  # type: ignore[arg-type]
            )
        except AppError as exc:
            return exc.status_code
        raise AssertionError("wrong password unexpectedly authenticated")

    with ThreadPoolExecutor(max_workers=12) as executor:
        statuses = list(executor.map(lambda _: attempt(), range(12)))

    assert statuses.count(401) == auth_module.LOGIN_FAILURE_LIMIT
    assert statuses.count(429) == 12 - auth_module.LOGIN_FAILURE_LIMIT


def test_current_user_requires_login() -> None:
    with pytest.raises(AppError) as error_info:
        deps_module.get_authenticated_user_id(authorization=None)

    assert error_info.value.status_code == 401
    assert error_info.value.code == ErrorCode.UNAUTHORIZED


def test_csrf_validation_uses_configured_cookie_and_header_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        app_env="production",
        jwt_secret_key="configured_jwt_secret_key_for_tests_123",
        csrf_cookie_name="custom_csrf_cookie",
        csrf_header_name="X-Custom-CSRF",
    )
    monkeypatch.setattr(deps_module, "get_settings", lambda: settings)
    matching_request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/preferences",
            "headers": [
                (b"cookie", b"custom_csrf_cookie=csrf-token"),
                (b"x-custom-csrf", b"csrf-token"),
            ],
        }
    )

    deps_module._validate_csrf_token(matching_request)

    default_header_request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/preferences",
            "headers": [
                (b"cookie", b"custom_csrf_cookie=csrf-token"),
                (b"x-csrf-token", b"csrf-token"),
            ],
        }
    )
    with pytest.raises(AppError) as error_info:
        deps_module._validate_csrf_token(default_header_request)

    assert error_info.value.code == ErrorCode.FORBIDDEN


def test_csrf_validation_rejects_untrusted_origin_even_with_matching_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        app_env="production",
        jwt_secret_key="configured_jwt_secret_key_for_tests_123",
        cors_allowed_origins="https://app.example.com",
    )
    monkeypatch.setattr(deps_module, "get_settings", lambda: settings)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/preferences",
            "headers": [
                (b"origin", b"https://attacker.example"),
                (b"cookie", b"interview_arena_csrf=csrf-token"),
                (b"x-csrf-token", b"csrf-token"),
            ],
        }
    )

    with pytest.raises(AppError) as error_info:
        deps_module._validate_csrf_token(request)

    assert error_info.value.code == ErrorCode.FORBIDDEN
    assert error_info.value.message == "请求来源不受信任。"


def test_csrf_validation_accepts_configured_referer_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        app_env="production",
        jwt_secret_key="configured_jwt_secret_key_for_tests_123",
        cors_allowed_origins="https://app.example.com",
    )
    monkeypatch.setattr(deps_module, "get_settings", lambda: settings)
    request = Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/api/preferences",
            "headers": [
                (b"referer", b"https://app.example.com/settings"),
                (b"cookie", b"interview_arena_csrf=csrf-token"),
                (b"x-csrf-token", b"csrf-token"),
            ],
        }
    )

    deps_module._validate_csrf_token(request)


def test_registration_rate_limit_is_shared_through_repository() -> None:
    class SharedRateLimitRepository(FakeUserRepository):
        def __init__(self) -> None:
            super().__init__()
            self.counts: dict[tuple[str, str, object], int] = {}

        def consume_auth_rate_limit(
            self,
            *,
            scope: str,
            identifier_hash: str,
            window_started_at: object,
            limit: int,
        ) -> bool:
            key = (scope, identifier_hash, window_started_at)
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key] <= limit

    repository = SharedRateLimitRepository()
    request = request_from_ip("10.10.10.10")
    for index in range(auth_module.REGISTRATION_ATTEMPT_LIMIT):
        register(
            AuthRequest(username=f"user-{index:02d}", password="secret-password"),
            http_request=request,
            users=repository,  # type: ignore[arg-type]
        )

    with pytest.raises(AppError) as error_info:
        register(
            AuthRequest(username="user-over-limit", password="secret-password"),
            http_request=request,
            users=repository,  # type: ignore[arg-type]
        )

    assert error_info.value.code == ErrorCode.TOO_MANY_REQUESTS


def test_jwt_default_secret_is_rejected_outside_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", Settings.jwt_secret_key)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        create_access_token(1)

    get_settings.cache_clear()


def test_jwt_example_placeholder_secret_is_rejected_outside_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "change_me_to_a_long_random_secret_at_least_32_chars")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        create_access_token(1)

    get_settings.cache_clear()


def test_current_user_accepts_legacy_bearer_token() -> None:
    repository = FakeUserRepository()
    repository.create("alice", hash_password("secret"))

    login_response = login(
        AuthRequest(username="alice", password="secret"),
        request_from_ip(),
        users=repository,  # type: ignore[arg-type]
    )

    assert login_response.id == 1
    assert login_response.username == "alice"
    assert login_response.display_name == "alice"

    user_id = deps_module.get_authenticated_user_id(
        authorization=f"Bearer {create_access_token(1)}"
    )
    current_user = get_current_user(
        user_id=user_id,
        users=repository,  # type: ignore[arg-type]
    )
    me_response = read_current_user(current_user)

    assert current_user.id == 1
    assert me_response.model_dump() == {
        "id": 1,
        "username": "alice",
        "display_name": "alice",
        "avatar_url": None,
        "external_model_consent": False,
    }


def test_login_endpoint_accepts_json_body_with_request_injection() -> None:
    repository = FakeUserRepository()
    repository.create("alice", hash_password("secret"))
    auth_module._login_failures.clear()
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: repository
    client = TestClient(app)

    response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    assert "access_token" not in response.json()
    assert "token_type" not in response.json()
    set_cookie = response.headers["set-cookie"]
    assert "interview_arena_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie


def test_update_current_user_display_name() -> None:
    repository = FakeUserRepository()
    current_user = repository.create("alice", hash_password("secret"))

    response = update_current_user(
        UserProfileUpdate(display_name="Alice Chen"),
        current_user=current_user,
        users=repository,  # type: ignore[arg-type]
    )

    assert response.model_dump() == {
        "id": 1,
        "username": "alice",
        "display_name": "Alice Chen",
        "avatar_url": None,
        "external_model_consent": False,
    }
    assert repository.get_by_id(1).display_name == "Alice Chen"  # type: ignore[union-attr]
    assert repository.get_by_id(1).display_name == "Alice Chen"  # type: ignore[union-attr]


def test_account_deletion_requires_current_password() -> None:
    current_user = UserRecord(
        id=1,
        username="alice",
        password_hash=hash_password("correct-password"),
    )

    with pytest.raises(AppError) as exc_info:
        delete_current_user_account(
            AccountDeleteRequest(password="wrong-password", confirmation="DELETE"),
            Response(),
            current_user=current_user,
            connection=object(),
        )

    assert exc_info.value.code == ErrorCode.UNAUTHORIZED


def test_upload_current_user_avatar_updates_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    repository = FakeUserRepository()
    current_user = repository.create("alice", hash_password("secret"))
    monkeypatch.setenv("AVATAR_UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    png_content = b"\x89PNG\r\n\x1a\n" + b"avatar"

    response = asyncio.run(
        upload_current_user_avatar(
            file=UploadFile(
                BytesIO(png_content),
                filename="avatar.png",
                headers=Headers({"content-type": "image/png"}),
            ),
            current_user=current_user,
            users=repository,  # type: ignore[arg-type]
        )
    )

    assert response.avatar_url is not None
    assert response.avatar_url.startswith("/api/uploads/avatars/user_1_")
    assert response.avatar_url.endswith(".png")
    assert (tmp_path / response.avatar_url.rsplit("/", 1)[-1]).read_bytes() == png_content
    assert repository.get_by_id(1).avatar_url == response.avatar_url  # type: ignore[union-attr]
    get_settings.cache_clear()


def test_upload_current_user_avatar_removes_previous_avatar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    repository = FakeUserRepository()
    current_user = repository.create("alice", hash_password("secret"))
    old_avatar = tmp_path / "old.png"
    old_avatar.write_bytes(b"\x89PNG\r\n\x1a\nold")
    repository.update_avatar_url(current_user.id, "/api/uploads/avatars/old.png")
    monkeypatch.setenv("AVATAR_UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()

    response = asyncio.run(
        upload_current_user_avatar(
            file=UploadFile(
                BytesIO(b"\x89PNG\r\n\x1a\nnew"),
                filename="avatar.png",
                headers=Headers({"content-type": "image/png"}),
            ),
            current_user=current_user,
            users=repository,  # type: ignore[arg-type]
        )
    )

    assert response.avatar_url is not None
    assert not old_avatar.exists()
    assert (tmp_path / response.avatar_url.rsplit("/", 1)[-1]).exists()
    get_settings.cache_clear()


def test_upload_current_user_avatar_preserves_previous_file_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    repository = FakeUserRepository()
    current_user = repository.create("alice", hash_password("secret"))
    old_avatar = tmp_path / "old.png"
    old_avatar.write_bytes(b"\x89PNG\r\n\x1a\nold")
    repository.update_avatar_url(current_user.id, "/api/uploads/avatars/old.png")
    repository.commit_error = RuntimeError("commit failed")
    monkeypatch.setenv("AVATAR_UPLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="commit failed"):
        asyncio.run(
            upload_current_user_avatar(
                file=UploadFile(
                    BytesIO(b"\x89PNG\r\n\x1a\nnew"),
                    filename="avatar.png",
                    headers=Headers({"content-type": "image/png"}),
                ),
                current_user=current_user,
                users=repository,  # type: ignore[arg-type]
            )
        )

    assert old_avatar.exists()
    assert list(tmp_path.glob("user_1_*.png")) == []
    get_settings.cache_clear()
