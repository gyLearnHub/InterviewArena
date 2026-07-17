from __future__ import annotations

from functools import lru_cache
from typing import cast

from redis import Redis
from redis.exceptions import RedisError, WatchError

from app.core.config import get_settings
from app.schemas.short_term_memory import ShortTermMemorySnapshot


class ShortTermMemoryStoreError(RuntimeError):
    pass


class ShortTermMemoryVersionConflict(ShortTermMemoryStoreError):
    pass


class RedisShortTermMemoryStore:
    def __init__(
        self,
        client: Redis,
        *,
        ttl_seconds: int,
        key_prefix: str = "interviewarena:stm:v1",
    ) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix

    @classmethod
    def from_settings(cls) -> RedisShortTermMemoryStore:
        settings = get_settings()
        client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.short_memory_redis_timeout_seconds,
            socket_timeout=settings.short_memory_redis_timeout_seconds,
            health_check_interval=30,
        )
        return cls(client, ttl_seconds=settings.short_memory_ttl_seconds)

    def key(self, user_id: int, interview_id: int) -> str:
        return f"{self.key_prefix}:user:{user_id}:interview:{interview_id}"

    def load(self, user_id: int, interview_id: int) -> ShortTermMemorySnapshot | None:
        try:
            value = cast(
                str | bytes | None,
                self.client.get(self.key(user_id, interview_id)),
            )
        except RedisError as exc:
            raise ShortTermMemoryStoreError("redis short-term memory read failed") from exc
        if value is None:
            return None
        try:
            snapshot = ShortTermMemorySnapshot.model_validate_json(value)
        except Exception as exc:
            raise ShortTermMemoryStoreError("redis short-term memory payload is invalid") from exc
        if snapshot.user_id != user_id or snapshot.interview_id != interview_id:
            raise ShortTermMemoryStoreError("redis short-term memory ownership mismatch")
        return snapshot

    def compare_and_set(
        self,
        snapshot: ShortTermMemorySnapshot,
        *,
        expected_version: int | None,
    ) -> ShortTermMemorySnapshot:
        key = self.key(snapshot.user_id, snapshot.interview_id)
        for attempt in range(2):
            try:
                with self.client.pipeline() as pipe:
                    pipe.watch(key)  # type: ignore[no-untyped-call]
                    raw = cast(str | bytes | None, pipe.get(key))
                    current_version = None
                    if raw is not None:
                        current_version = ShortTermMemorySnapshot.model_validate_json(raw).version
                    if current_version != expected_version:
                        pipe.unwatch()
                        raise ShortTermMemoryVersionConflict(
                            f"expected version {expected_version}, got {current_version}"
                        )
                    stored = snapshot.model_copy(update={"version": (current_version or 0) + 1})
                    pipe.multi()
                    pipe.setex(key, self.ttl_seconds, stored.model_dump_json())
                    pipe.execute()
                    return stored
            except WatchError as exc:
                if attempt == 0:
                    continue
                raise ShortTermMemoryVersionConflict("redis transaction conflicted") from exc
            except ShortTermMemoryVersionConflict:
                raise
            except (RedisError, ValueError) as exc:
                raise ShortTermMemoryStoreError("redis short-term memory write failed") from exc
        raise ShortTermMemoryVersionConflict("redis transaction conflicted")

    def delete(self, user_id: int, interview_id: int) -> bool:
        try:
            return bool(self.client.delete(self.key(user_id, interview_id)))
        except RedisError as exc:
            raise ShortTermMemoryStoreError("redis short-term memory delete failed") from exc

    def delete_many(self, user_id: int, interview_ids: list[int]) -> int:
        if not interview_ids:
            return 0
        keys = [self.key(user_id, interview_id) for interview_id in interview_ids]
        try:
            return cast(int, self.client.delete(*keys))
        except RedisError as exc:
            raise ShortTermMemoryStoreError("redis short-term memory batch delete failed") from exc

    def ttl(self, user_id: int, interview_id: int) -> int:
        try:
            value = cast(int, self.client.ttl(self.key(user_id, interview_id)))
            return int(value)
        except RedisError as exc:
            raise ShortTermMemoryStoreError("redis short-term memory ttl read failed") from exc

    def close(self) -> None:
        self.client.close()


@lru_cache
def get_short_term_memory_store() -> RedisShortTermMemoryStore:
    return RedisShortTermMemoryStore.from_settings()


def close_short_term_memory_store() -> None:
    if get_short_term_memory_store.cache_info().currsize == 0:
        return
    store = get_short_term_memory_store()
    store.close()
    get_short_term_memory_store.cache_clear()
