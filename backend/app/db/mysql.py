from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from queue import Empty, Full, LifoQueue
from threading import Lock
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.core.config import get_settings


@dataclass(frozen=True)
class MySQLConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"


def parse_mysql_url(database_url: str) -> MySQLConfig:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise ValueError("DATABASE_URL must use mysql or mysql+pymysql scheme")
    database = parsed.path.lstrip("/")
    if not database:
        raise ValueError("DATABASE_URL must include a database name")
    query = parse_qs(parsed.query)
    return MySQLConfig(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=database,
        charset=query.get("charset", ["utf8mb4"])[0],
    )


def create_connection(database_url: str | None = None) -> Any:
    import pymysql

    settings = get_settings()
    config = parse_mysql_url(database_url or settings.database_url)
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        charset=config.charset,
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
        init_command="SET time_zone = '+00:00'",
        connect_timeout=settings.mysql_connect_timeout_seconds,
        read_timeout=settings.mysql_read_timeout_seconds,
        write_timeout=settings.mysql_write_timeout_seconds,
    )


class MySQLConnectionPool:
    def __init__(
        self,
        *,
        max_size: int,
        acquire_timeout_seconds: int,
        connection_factory: Any = create_connection,
    ) -> None:
        self.max_size = max(1, max_size)
        self.acquire_timeout_seconds = max(1, acquire_timeout_seconds)
        self.connection_factory = connection_factory
        self._idle: LifoQueue[Any] = LifoQueue(maxsize=self.max_size)
        self._lock = Lock()
        self._created = 0
        self._closed = False

    def acquire(self) -> Any:
        if self._closed:
            raise RuntimeError("mysql connection pool is closed")
        for _attempt in range(2):
            try:
                connection = self._idle.get_nowait()
            except Empty:
                connection = self._create_or_wait()
            try:
                ping = getattr(connection, "ping", None)
                if callable(ping):
                    ping()
                return connection
            except Exception:
                self.discard(connection)
        raise ConnectionError("mysql connection validation failed")

    def release(self, connection: Any) -> None:
        if self._closed or not _connection_is_open(connection):
            self.discard(connection)
            return
        try:
            self._idle.put_nowait(connection)
        except Full:
            self.discard(connection)

    def discard(self, connection: Any) -> None:
        try:
            connection.close()
        finally:
            with self._lock:
                self._created = max(0, self._created - 1)

    def close(self) -> None:
        self._closed = True
        while True:
            try:
                connection = self._idle.get_nowait()
            except Empty:
                break
            self.discard(connection)

    @property
    def created_connections(self) -> int:
        with self._lock:
            return self._created

    def _create_or_wait(self) -> Any:
        should_create = False
        with self._lock:
            if not self._closed and self._created < self.max_size:
                self._created += 1
                should_create = True
        if should_create:
            try:
                return self.connection_factory()
            except Exception:
                with self._lock:
                    self._created = max(0, self._created - 1)
                raise
        try:
            return self._idle.get(timeout=self.acquire_timeout_seconds)
        except Empty as exc:
            raise TimeoutError("mysql connection pool acquire timeout") from exc


_POOL: MySQLConnectionPool | None = None
_POOL_LOCK = Lock()


def get_connection_pool() -> MySQLConnectionPool:
    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                settings = get_settings()
                _POOL = MySQLConnectionPool(
                    max_size=settings.mysql_pool_size,
                    acquire_timeout_seconds=settings.mysql_pool_acquire_timeout_seconds,
                )
    return _POOL


def close_connection_pool() -> None:
    global _POOL
    with _POOL_LOCK:
        pool = _POOL
        _POOL = None
    if pool is not None:
        pool.close()


@contextmanager
def mysql_connection(database_url: str | None = None) -> Iterator[Any]:
    pool = get_connection_pool() if database_url is None else None
    connection = pool.acquire() if pool is not None else create_connection(database_url)
    reusable = True
    try:
        yield connection
        connection.commit()
    except Exception:
        try:
            connection.rollback()
        except Exception:
            reusable = False
        raise
    finally:
        if pool is None:
            connection.close()
        elif reusable and _connection_is_open(connection):
            pool.release(connection)
        else:
            pool.discard(connection)


def _connection_is_open(connection: Any) -> bool:
    open_value = getattr(connection, "open", True)
    return bool(open_value)
