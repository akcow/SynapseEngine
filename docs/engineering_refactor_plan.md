# 从原型到工业级：记忆引擎工程化重构路线图

这份文档旨在指导你如何将当前的 `mini_memory_engine` 演化为一个可支撑生产环境的成熟系统。

## 第一阶段：数据底座与一致性 (Persistence & Consistency)

### 1.1 从内存到数据库 (SQLAlchemy + PostgreSQL)
- **行动**：将 `InMemoryDB` 替换为真正的数据库存储。
- **理由**：内存存储不可靠，且无法处理复杂查询。推荐使用 PostgreSQL，因为它有成熟的事务支持和 `pgvector` 扩展。
- **关键点**：实现数据库迁移逻辑（如使用 Alembic），确保 schema 演化可控。

### 1.2 向量数据库集成
- **行动**：使用专门的向量库（如 Qdrant, ChromaDB, 或 pgvector）。
- **理由**：当 Observation 达到万级以上，暴力遍历计算余弦相似度将成为瓶颈。
- **关键点**：引入 HNSW 索引，支持高效的相似度检索。

---

## 第二阶段：任务治理与异步化 (Task Governance)

### 2.1 分布式任务队列 (Celery / Temporal)
- **行动**：将 `asyncio.Queue` 替换为分布式队列。
- **理由**：单机内存队列在进程崩溃时会丢失任务。分布式队列支持持久化、重试和多 Worker 消费。
- **关键点**：实现“死信队列（DLQ）”，记录多次重试失败的任务进行人工审计。

### 2.2 幂等性设计 (Idempotency)
- **行动**：为每个 `QueueTask` 增加 `task_id`，在处理前检查该任务是否已完成。
- **理由**：网络波动或 Worker 重启会导致同一个任务被多次执行。
- **关键点**：在数据库中记录任务执行状态，确保“提取”或“合并”操作不会产生重复的 Observation。

---

## 第三阶段：代码工程化与可读性 (Refactoring & Quality)

### 3.1 目录结构解耦 (Modularization)
- **行动**：按领域（Domain）拆分文件，避免“上帝文件”。
- **推荐结构**：
  - `app/models/`: 数据结构
  - `app/services/`: 业务逻辑（Extractor, Dreamer）
  - `app/core/`: 引擎核心调度
  - `app/api/`: 接口定义

### 3.2 依赖注入 (Dependency Injection)
- **行动**：使用 DI 框架（如 `dependency-injector`）或简单的构造函数注入。
- **理由**：解耦组件创建逻辑，方便编写 Unit Tests（通过注入 Mock 对象）。

### 3.3 类型安全 (Pydantic)
- **行动**：将 `dataclass` 升级为 `Pydantic` 模型。
- **理由**：Pydantic 提供强大的运行时数据校验和设置管理（Settings Management）。

---

## 第四阶段：稳定性与可观测性 (Observability)

### 4.1 结构化日志 (Structured Logging)
- **行动**：引入 `structlog` 或标准 `logging` 库。
- **理由**：`print` 无法追踪线上问题。需要记录 `request_id`, `session_id`, `latency` 等关键元数据。

### 4.2 对账与自愈 (Reconciliation Loop)
- **行动**：实现一个独立的 `Reconciler` 后台进程。
- **理由**：主流程中写入向量库可能会失败。对账进程定时扫描“有数据库记录但无向量记录”的 Observation 并补齐。

### 4.3 性能监控 (Metrics & Tracing)
- **行动**：接入 Prometheus 监控指标，使用 OpenTelemetry 进行分布式追踪。
- **理由**：快速定位 LLM 调用慢、任务堆积等性能瓶颈。

---

## 第五阶段：成本与策略优化 (Cost & Strategy)

### 5.1 智能 Token 预算
- **行动**：在生成 Summary 或 Context 时，精确计算 Token 消耗。
- **关键点**：实现动态优先级策略——在 Context 紧张时优先保留 `insight` 级别的记忆，丢弃 `explicit` 级别的碎片。

### 5.2 缓存层
- **行动**：引入 Redis 缓存高频查询的 Memory Context。
- **理由**：减少对数据库和向量库的重复压力。
