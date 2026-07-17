from datetime import datetime
from uuid import uuid4

import pytest
from app.schemas.short_term_memory import ShortTermMemorySnapshot
from app.services.short_term_memory_store import (
    RedisShortTermMemoryStore,
    ShortTermMemoryVersionConflict,
)
from redis import Redis
from redis.exceptions import RedisError


def test_real_redis_ttl_cas_and_delete() -> None:
    client = Redis.from_url(
        "redis://127.0.0.1:6379/0",
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    try:
        client.ping()
    except RedisError:
        pytest.skip("local Redis is not available")

    store = RedisShortTermMemoryStore(
        client,
        ttl_seconds=604800,
        key_prefix=f"interviewarena:test:stm:{uuid4().hex}",
    )
    snapshot = ShortTermMemorySnapshot(
        user_id=901,
        interview_id=902,
        updated_at=datetime.utcnow(),
    )
    try:
        first = store.compare_and_set(snapshot, expected_version=None)
        second = store.compare_and_set(snapshot, expected_version=first.version)

        assert first.version == 1
        assert second.version == 2
        assert 604790 <= store.ttl(901, 902) <= 604800
        with pytest.raises(ShortTermMemoryVersionConflict):
            store.compare_and_set(snapshot, expected_version=first.version)
        assert store.delete(901, 902) is True
        assert store.load(901, 902) is None
        store.compare_and_set(snapshot, expected_version=None)
        store.compare_and_set(
            snapshot.model_copy(update={"interview_id": 903}),
            expected_version=None,
        )
        assert store.delete_many(901, [902, 903]) == 2
        assert store.load(901, 902) is None
        assert store.load(901, 903) is None
    finally:
        client.delete(store.key(901, 902))
        client.delete(store.key(901, 903))
        store.close()
