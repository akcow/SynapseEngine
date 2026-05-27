import time
import logging
import asyncio
from functools import wraps
from prometheus_client import Counter, Gauge, generate_latest, REGISTRY, CONTENT_TYPE_LATEST
from fastapi import Response, Request

logger = logging.getLogger(__name__)

# --- Prometheus Metrics (指标监控) ---

api_requests_total = Counter(
    "api_requests_total", 
    "Total API requests", 
    ["method", "endpoint", "status_code"]
)

tasks_processed_total = Counter(
    "tasks_processed_total", 
    "Total memory tasks processed", 
    ["task_type", "status"]
)

pending_tasks_gauge = Gauge(
    "pending_tasks_current", 
    "Current number of pending tasks in the database queue"
)

async def metrics_endpoint(request: Request):
    """供 Prometheus / Grafana 抓取指标的端点"""
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

# --- Tracing (轻量级耗时追踪装饰器) ---

def track_latency(name: str = None):
    """
    轻量级性能追踪装饰器。自动计算耗时，并依托 logging 注入当前 request_id。
    """
    def decorator(func):
        func_name = name or func.__name__
        
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    return await func(*args, **kwargs)
                finally:
                    cost = time.time() - start
                    logger.info(f"[Tracing] {func_name} execution cost: {cost:.4f}s")
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    return func(*args, **kwargs)
                finally:
                    cost = time.time() - start
                    logger.info(f"[Tracing] {func_name} execution cost: {cost:.4f}s")
            return sync_wrapper
    return decorator
