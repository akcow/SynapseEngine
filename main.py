import asyncio
import os
import sys
from contextlib import asynccontextmanager
import uuid
import logging

from fastapi import FastAPI, Request
import uvicorn

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.logger import setup_logging, request_id_ctx
setup_logging()
logger = logging.getLogger(__name__)

from app.core.engine import MemoryEngine
from app.core.database import init_db
from app.utils.vectorizer import HashVectorizer
from app.services.matcher import MatchingSpecialist
from app.core.storage import InMemoryDB
from app.api.routes import router
from app.services.reconciler import Reconciler

# 第三板斧：生命周期大管家
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 开店准备 (Startup) ---
    logger.info("[Lifespan] 正在初始化数据库和调度引擎...")
    os.environ["EXTRACTOR_MODE"] = "rule"  # 为测试保持确定性
    init_db()
    
    my_db = InMemoryDB()
    my_vectorizer = HashVectorizer()
    my_matcher = MatchingSpecialist()

    # 将外部组件注入到主厨（引擎）中
    engine = MemoryEngine(
        db=my_db,
        vectorizer=my_vectorizer,
        matcher=my_matcher
    )
    
    # 将主厨存入状态，这样服务员(Routes)也能随时找到他
    app.state.engine = engine
    
    # 初始化对账进程
    reconciler = Reconciler(
        db=my_db,
        vectorizer=my_vectorizer,
        index_adder=lambda obs, obsd, oid, emb: engine._get_index(obs, obsd).add(oid, emb)
    )
    
    # 启动后台任务处理死循环
    worker = asyncio.create_task(engine.worker_loop())
    reconciler_task = asyncio.create_task(reconciler.run_loop())
    logger.info("[Lifespan] 记忆引擎启动完毕！开门接客...")
    
    # 交出控制权，开始营业处理 HTTP 请求
    yield 
    
    # --- 打烊收尾 (Shutdown) ---
    logger.info("[Lifespan] 收到关机信号，正在停机清理...")
    engine.stop()
    reconciler.stop()
    worker.cancel()
    reconciler_task.cancel()
    try:
        await worker
        await reconciler_task
    except asyncio.CancelledError:
        pass
    logger.info("[Lifespan] 引擎和工人已安全关闭。拜拜！")

# 实例化 FastAPI 对象
app = FastAPI(
    title="Mini Memory Engine API",
    description="从原型迈向工业级的记忆引擎接口",
    version="1.0.0",
    lifespan=lifespan
)

# 挂载我们刚刚写的服务员（路由）
app.include_router(router)

from app.core.telemetry import metrics_endpoint, api_requests_total

app.add_route("/metrics", metrics_endpoint, methods=["GET"])

@app.middleware("http")
async def track_request(request: Request, call_next):
    req_id = str(uuid.uuid4())[:8]
    token = request_id_ctx.set(req_id)
    try:
        response = await call_next(request)
        
        # 记录 Prometheus 流量指标 (剔除自身采集)
        if request.url.path != "/metrics":
            api_requests_total.labels(
                method=request.method, 
                endpoint=request.url.path, 
                status_code=str(response.status_code)
            ).inc()
            
        return response
    finally:
        request_id_ctx.reset(token)

if __name__ == "__main__":
    # 使用 Uvicorn 启动 ASGI 服务器
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
