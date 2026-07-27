import re
from typing import Any

from fastapi import status

from app.core.errors import AppError, ErrorCode
from app.repositories.preferences import PreferencesRepository
from app.repositories.users import UserRecord

CONSENT_REQUIRED_MESSAGE = (
    "使用模型能力前，请在设置中明确同意将脱敏后的简历、岗位描述和面试内容发送给"
    "第三方模型服务。"
)
_SENSITIVE_KEYS = {
    "name",
    "full_name",
    "姓名",
    "真实姓名",
    "phone",
    "mobile",
    "telephone",
    "电话",
    "手机",
    "手机号",
    "email",
    "邮箱",
    "address",
    "地址",
    "住址",
    "wechat",
    "微信",
    "id_number",
    "身份证",
    "身份证号",
}
_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)|(?<!\d)\d{15}(?!\d)")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)")
_LABELED_VALUE_RE = re.compile(
    r"(?im)^(\s*(?:姓名|真实姓名|电话|手机|手机号|邮箱|地址|住址|微信|身份证号?)"
    r"\s*[:：]\s*).+$"
)


def require_external_model_consent(user: UserRecord) -> None:
    require_external_model_consent_value(user.external_model_consent)


def require_external_model_consent_value(consent: bool) -> None:
    if not consent:
        raise _consent_required_error()


def ensure_external_model_consent(connection: Any, user_id: int) -> None:
    if not PreferencesRepository(connection).get_external_model_consent(user_id):
        raise _consent_required_error()


def redact_text(value: str) -> str:
    redacted = _LABELED_VALUE_RE.sub(r"\1[已脱敏]", value)
    redacted = _EMAIL_RE.sub("[邮箱已脱敏]", redacted)
    redacted = _ID_CARD_RE.sub("[证件号已脱敏]", redacted)
    return _PHONE_RE.sub("[手机号已脱敏]", redacted)


def redact_model_payload(value: Any, *, key: str | None = None) -> Any:
    if key is not None and key.strip().casefold() in _SENSITIVE_KEYS:
        return "[已脱敏]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            str(item_key): redact_model_payload(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact_model_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_model_payload(item) for item in value]
    return value


def _consent_required_error() -> AppError:
    return AppError(
        ErrorCode.FORBIDDEN,
        status.HTTP_403_FORBIDDEN,
        message=CONSENT_REQUIRED_MESSAGE,
    )
