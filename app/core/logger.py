import logging
import contextvars
from typing import Optional

# 定义 ContextVar，默认值为 "-" 以避免打印时报错
request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id_ctx", default="-"
)

class RequestContextFilter(logging.Filter):
    """
    一个日志过滤器，用于从 ContextVar 中提取 request_id 并注入到 LogRecord 中，
    从而让 format 字符串可以使用 %(request_id)s
    """
    def filter(self, record: logging.LogRecord) -> bool:
        req_id = request_id_ctx.get()
        # 如果上下文中没有值，或者值为 None，则回退为 "-"
        record.request_id = req_id if req_id else "-"
        return True

def setup_logging(level: int = logging.INFO):
    """
    初始化全局日志配置
    """
    # 重新配置 basicConfig，加入自定义的 %(request_id)s
    # 注意：如果之前已经配置过 logging，basicConfig 可能不起作用，因此这里加上 force=True
    logging.basicConfig(
        level=level,
        format="%(asctime)s - [%(request_id)s] - %(name)s - %(levelname)s - %(message)s",
        force=True
    )
    
    # 获取我们自定义的 Filter
    context_filter = RequestContextFilter()
    
    # 挂载到 root logger 的所有 handlers 上
    for handler in logging.root.handlers:
        handler.addFilter(context_filter)
