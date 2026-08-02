from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CacheService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._memory: dict[str, str] = {}
        self._redis = None
        if self.settings.use_inmemory_fallback:
            logger.info("Using in-memory cache (Redis probe skipped)")
            return
        try:
            import redis

            client = redis.Redis.from_url(self.settings.redis_url, decode_responses=True, socket_connect_timeout=1)
            client.ping()
            self._redis = client
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis unavailable, using memory cache: %s", exc)

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        payload = json.dumps(value)
        if self._redis is not None:
            try:
                self._redis.setex(key, ttl, payload)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis set failed: %s", exc)
        self._memory[key] = payload

    def get(self, key: str) -> Any | None:
        if self._redis is not None:
            try:
                raw = self._redis.get(key)
                return json.loads(raw) if raw else None
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis get failed: %s", exc)
        raw = self._memory.get(key)
        return json.loads(raw) if raw else None


cache_service = CacheService()
