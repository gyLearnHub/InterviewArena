import re
from urllib.parse import urlsplit

from app.core.config import Settings


def configured_origins(settings: Settings) -> list[str]:
    return [
        origin.strip().rstrip("/")
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ]


def is_origin_allowed(origin: str, settings: Settings) -> bool:
    normalized = origin.strip().rstrip("/")
    if not normalized:
        return False
    if normalized in configured_origins(settings):
        return True
    pattern = settings.cors_allowed_origin_regex.strip()
    return bool(pattern and re.fullmatch(pattern, normalized))


def request_source_origin(origin: str | None, referer: str | None) -> str | None:
    if origin:
        return origin.strip().rstrip("/")
    if not referer:
        return None
    parsed = urlsplit(referer)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
