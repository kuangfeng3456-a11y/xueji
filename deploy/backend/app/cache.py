import json
import threading
import time
from typing import Any, Optional

from .config import settings


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            expire_at, value = item
            if expire_at and expire_at < time.time():
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, ttl: int = 300) -> None:
        with self._lock:
            self._data[key] = (time.time() + ttl if ttl else 0, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def incr(self, key: str, ttl: int = 60) -> int:
        with self._lock:
            item = self._data.get(key)
            now = time.time()
            if not item or (item[0] and item[0] < now):
                # 计数窗口已过期，重新从 1 开始，避免限流永久生效
                count, expire_at = 1, now + ttl
            else:
                expire_at, value = item
                count = int(value) + 1
            self._data[key] = (expire_at, str(count))
            return count


class Cache:
    def __init__(self) -> None:
        self._fallback = MemoryCache()
        self._redis = None
        if settings.REDIS_URL:
            try:
                import redis

                ssl_options = {}
                if settings.REDIS_SSL_CA:
                    ssl_options["ssl_ca_certs"] = settings.REDIS_SSL_CA
                client = redis.Redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=3,
                    socket_timeout=3,
                    health_check_interval=30,
                    **ssl_options,
                )
                client.ping()
                self._redis = client
            except Exception:
                self._redis = None

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def ping(self) -> bool:
        if self._redis is None:
            return True
        try:
            return bool(self._redis.ping())
        except Exception:
            return False

    def info(self) -> dict:
        if self._redis is None:
            return {"backend": "memory"}
        try:
            raw = self._redis.info()
            return {
                "backend": "redis",
                "version": raw.get("redis_version", ""),
                "used_memory_human": raw.get("used_memory_human", ""),
                "connected_clients": raw.get("connected_clients", 0),
            }
        except Exception:
            return {"backend": "redis", "version": "", "used_memory_human": "", "connected_clients": 0}

    def get_json(self, key: str) -> Optional[Any]:
        raw = None
        if self._redis is not None:
            try:
                raw = self._redis.get(key)
            except Exception:
                raw = None
        if raw is None:
            raw = self._fallback.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def set_json(self, key: str, value: Any, ttl: int = 300) -> None:
        raw = json.dumps(value, ensure_ascii=False)
        if self._redis is not None:
            try:
                self._redis.setex(key, ttl, raw)
            except Exception:
                pass
        self._fallback.set(key, raw, ttl)

    def delete(self, key: str) -> None:
        if self._redis is not None:
            try:
                self._redis.delete(key)
            except Exception:
                pass
        self._fallback.delete(key)

    def incr(self, key: str, ttl: int = 60) -> int:
        if self._redis is not None:
            try:
                count = int(self._redis.incr(key))
                if count == 1:
                    self._redis.expire(key, ttl)
                return count
            except Exception:
                pass
        return self._fallback.incr(key, ttl)


cache = Cache()