import pytest
from app.core.errors import AppError, ErrorCode
from app.repositories.users import UserRecord
from app.services.privacy import (
    CONSENT_REQUIRED_MESSAGE,
    ensure_external_model_consent,
    redact_model_payload,
    require_external_model_consent,
)


class _ConsentConnection:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row

    def cursor(self) -> "_ConsentConnection":
        return self

    def __enter__(self) -> "_ConsentConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _sql: str, _params: tuple[object, ...]) -> None:
        return None

    def fetchone(self) -> dict[str, object] | None:
        return self.row


def test_external_model_use_requires_explicit_consent() -> None:
    user = UserRecord(id=1, username="alice", password_hash="hash")

    with pytest.raises(AppError) as exc_info:
        require_external_model_consent(user)

    assert user.external_model_consent is False
    assert exc_info.value.code == ErrorCode.FORBIDDEN
    assert exc_info.value.status_code == 403
    assert exc_info.value.message == CONSENT_REQUIRED_MESSAGE


def test_payload_redaction_preserves_non_identifying_interview_evidence() -> None:
    payload = redact_model_payload(
        {
            "name": "Alice",
            "project": {
                "description": "将接口 P95 从 800ms 降到 220ms",
                "address": "上海市某路 1 号",
            },
        }
    )

    assert payload["name"] == "[已脱敏]"
    assert payload["project"]["address"] == "[已脱敏]"
    assert payload["project"]["description"] == "将接口 P95 从 800ms 降到 220ms"


def test_worker_rechecks_current_consent_version() -> None:
    stale_consent = _ConsentConnection(
        {
            "external_model_consent_at": object(),
            "external_model_consent_version": "older-version",
        }
    )

    with pytest.raises(AppError) as exc_info:
        ensure_external_model_consent(stale_consent, 1)

    assert exc_info.value.code == ErrorCode.FORBIDDEN
