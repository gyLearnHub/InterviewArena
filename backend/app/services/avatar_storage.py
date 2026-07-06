from contextlib import suppress
from pathlib import Path
from urllib.parse import unquote
from uuid import uuid4

from fastapi import status

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode
from app.services.resume_parser import project_root

MAX_AVATAR_BYTES = 2 * 1024 * 1024
AVATAR_PUBLIC_PREFIX = "/api/uploads/avatars"
SUPPORTED_AVATAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def resolve_avatar_upload_dir(settings: Settings | None = None) -> Path:
    configured = Path((settings or get_settings()).avatar_upload_dir)
    if not configured.is_absolute():
        configured = project_root() / configured
    return configured


def validate_avatar_upload(filename: str, content_type: str | None, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_AVATAR_EXTENSIONS:
        raise AppError(ErrorCode.INVALID_UPLOAD_TYPE, status.HTTP_400_BAD_REQUEST)

    normalized_content_type = (content_type or "").lower()
    if normalized_content_type and normalized_content_type not in {
        "image/jpeg",
        "image/png",
        "image/webp",
    }:
        raise AppError(ErrorCode.INVALID_UPLOAD_TYPE, status.HTTP_400_BAD_REQUEST)

    if not _content_matches_extension(extension, content):
        raise AppError(ErrorCode.INVALID_UPLOAD_TYPE, status.HTTP_400_BAD_REQUEST)

    return ".jpg" if extension == ".jpeg" else extension


def make_avatar_path(user_id: int, extension: str, upload_dir: Path) -> Path:
    return upload_dir / f"user_{user_id}_{uuid4().hex}{extension}"


def avatar_public_url(path: Path) -> str:
    return f"{AVATAR_PUBLIC_PREFIX}/{path.name}"


def delete_avatar_by_public_url(
    avatar_url: str | None,
    upload_dir: Path,
    *,
    keep_url: str | None = None,
) -> None:
    if not avatar_url or avatar_url == keep_url:
        return
    prefix = f"{AVATAR_PUBLIC_PREFIX}/"
    if not avatar_url.startswith(prefix):
        return

    filename = unquote(avatar_url[len(prefix):])
    if not filename or Path(filename).name != filename:
        return

    upload_root = upload_dir.resolve()
    target = (upload_root / filename).resolve()
    if target.parent != upload_root:
        return
    with suppress(FileNotFoundError, OSError):
        target.unlink()


def _content_matches_extension(extension: str, content: bytes) -> bool:
    if extension in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False
