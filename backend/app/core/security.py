import base64
import binascii
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode

_PASSWORD_ITERATIONS = 210_000
_PASSWORD_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_PASSWORD_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PASSWORD_ITERATIONS,
    )
    return f"pbkdf2_sha256${_PASSWORD_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = _b64decode(salt_text)
        expected_digest = _b64decode(digest_text)
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return _encode_jwt(payload, settings.jwt_secret_key, settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    payload = _decode_jwt(token, settings.jwt_secret_key, settings.jwt_algorithm)
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(datetime.now(UTC).timestamp()):
        raise AppError(ErrorCode.UNAUTHORIZED, status_code=401)
    return payload


def _encode_jwt(payload: dict[str, Any], secret: str, algorithm: str) -> str:
    if algorithm != "HS256":
        raise AppError(ErrorCode.INTERNAL_ERROR, status_code=500, message="不支持的 JWT 算法。")
    header = {"alg": algorithm, "typ": "JWT"}
    signing_input = ".".join(
        [
            _b64encode_json(header),
            _b64encode_json(payload),
        ]
    )
    signature = hmac.new(
        secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64encode(signature)}"


def _decode_jwt(token: str, secret: str, algorithm: str) -> dict[str, Any]:
    if algorithm != "HS256":
        raise AppError(ErrorCode.INTERNAL_ERROR, status_code=500, message="不支持的 JWT 算法。")
    try:
        header_text, payload_text, signature_text = token.split(".")
        signing_input = f"{header_text}.{payload_text}"
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()
        actual_signature = _b64decode(signature_text)
        header = json.loads(_b64decode(header_text).decode("utf-8"))
        payload = json.loads(_b64decode(payload_text).decode("utf-8"))
    except (ValueError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
        raise AppError(ErrorCode.UNAUTHORIZED, status_code=401) from None

    is_valid_signature = hmac.compare_digest(actual_signature, expected_signature)
    if header.get("alg") != algorithm or not is_valid_signature:
        raise AppError(ErrorCode.UNAUTHORIZED, status_code=401)
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.UNAUTHORIZED, status_code=401)
    return payload


def _b64encode_json(value: dict[str, Any]) -> str:
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _b64encode(data)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
