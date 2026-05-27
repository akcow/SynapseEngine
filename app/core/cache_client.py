import logging
import os
import json
from cachetools import TTLCache
from typing import Any, Optional, List
import redis

from app.models.message import Message

logger = logging.getLogger(__name__)

# 如果环境中配置了 REDIS_URL，或者本地 6379 端口有 Redis，就尝试连接
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis_client = None
try:
    _redis = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    _redis.ping() # 测试连接
    redis_client = _redis
    logger.info("Connected to real Redis service.")
except Exception as e:
    logger.warning(f"Failed to connect to Redis at {REDIS_URL}: {e}. Falling back to in-memory cache.")

# 内存回退模式（当 Redis 挂了或没启动时）
_mem_cache = TTLCache(maxsize=1000, ttl=300)

def _serialize(value: List[Message]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in value])

def _deserialize(data: str) -> List[Message]:
    return [Message.model_validate(m) for m in json.loads(data)]

def safe_cache_set(key: str, value: List[Message]) -> None:
    """Best-effort cache set"""
    try:
        if redis_client:
            redis_client.set(key, _serialize(value), ex=300)
            logger.debug(f"[Redis] Cache set for key {key}")
        else:
            _mem_cache[key] = value
            logger.debug(f"[Mem] Cache set for key {key}")
    except Exception:
        logger.warning(f"Cache set failed for key {key}", exc_info=True)

def safe_cache_get(key: str) -> Optional[List[Message]]:
    """获取缓存"""
    try:
        if redis_client:
            data = redis_client.get(key)
            if data:
                return _deserialize(data)
            return None
        else:
            return _mem_cache.get(key)
    except Exception as e:
        logger.warning(f"Cache get failed for key {key}: {e}", exc_info=True)
        return None

def safe_cache_delete_prefix(prefix: str) -> None:
    """Best-effort cache delete for invalidation (前缀删除)"""
    try:
        if redis_client:
            cursor = '0'
            while cursor != 0:
                cursor, keys = redis_client.scan(cursor=cursor, match=f"{prefix}*")
                if keys:
                    redis_client.delete(*keys)
            logger.debug(f"[Redis] Cache invalidated for prefix {prefix}")
        else:
            keys_to_delete = [k for k in _mem_cache.keys() if k.startswith(prefix)]
            for k in keys_to_delete:
                del _mem_cache[k]
            logger.debug(f"[Mem] Cache invalidated for prefix {prefix}")
    except Exception:
        logger.warning(f"Cache delete failed for prefix {prefix}", exc_info=True)

def session_msgs_cache_prefix(session_id: str) -> str:
    return f"session_msgs:{session_id}:"

def session_msgs_cache_key(session_id: str, token_limit: Optional[int]) -> str:
    return f"{session_msgs_cache_prefix(session_id)}limit_{token_limit}"
