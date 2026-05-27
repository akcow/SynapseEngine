# 🧠 SynapseEngine

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)

*其他语言版本: [English](README.md), [简体中文](README_zh.md).*

---

**SynapseEngine** 是一个受 [Honcho](https://github.com/plastic-labs/honcho) 启发的轻量级、工业级 AI 记忆系统。它作为一个独立的后台服务运行，通过标准的 RESTful API 为您的 Agent 和 LLM 应用提供状态化、长期的记忆能力。

它不仅仅是一个聊天记录器，而是一个具备“自我进化”能力的系统，能够自动提取事实、总结上下文、解决冲突，并构建多视角的用户画像。

## ✨ 核心特性
- 🚀 **FastAPI 后端**：开箱即用、可扩展的 HTTP API 层，适用于多智能体系统。
- 💾 **PostgreSQL & 向量支持**：通过 SQLAlchemy 实现持久化存储，并设计了向量索引抽象层。
- 🧬 **记忆演化**：实现了分层记忆模型（`explicit(碎片)` -> `deductive(事实)` -> `inductive(画像)` -> `insight(智慧)`）。
- 🔄 **异步处理循环**：非阻塞的消息摄入；记忆的提取与合并完全在后台异步进行。
- 🛠️ **模块化架构**：清晰的领域驱动设计，随时准备好应对生产环境的挑战。

## 🧠 核心理念与概念字典
为了极致的轻量与跨平台，我们抛弃了厚重的 SDK 封装，只提供纯粹的后端服务核心。
- **Message (消息)**：对话的原子单位，每次存入会自动触发后台记忆抽取。
- **Observation (记忆切片)**：从消息中提取的语义事实，具有明确的层级标签（`explicit`, `deductive`, `inductive`, `insight`）。
- **Summary (摘要)**：每积累 N 条消息，系统在后台自动进行的上下文压缩。
- **Recursive Dream (递归梦境)**：后台静默运行的核心算法，自动将底层的零碎事实聚类、碰撞，最终升维成对用户的高维洞察（画像与智慧）。

## 📦 系统架构

```mermaid
graph TD
    Client[业务应用 / Agent] -->|POST 存入消息| API[FastAPI /sessions/*/messages]
    API --> DB[(PostgreSQL)]
    API -.->|派发异步任务| TaskQueue[后台任务队列]
    
    subgraph 异步工作流 (Worker Loop)
        TaskQueue --> Extractor[LLM 提取器]
        Extractor -->|生成初步记忆| Obs[Observation]
        Obs --> Matcher[语义匹配器]
        Matcher -->|冲突解决与合并| Consolidator[记忆整合器]
    end
    
    Consolidator --> DB
    Consolidator --> VectorDB[(向量数据库 / 索引)]
    
    Client -->|GET 查询记忆| SearchAPI[FastAPI /memories]
    SearchAPI --> VectorDB
```

## 🚀 快速开始
**1. 安装部署**
```bash
git clone https://github.com/yourusername/SynapseEngine.git
cd SynapseEngine
pip install -r requirements.txt
```
**2. 环境配置**
```bash
cp .env.example .env
```
编辑 `.env` 文件，配置您的参数：
```env
DATABASE_URL=postgresql://user:password@localhost:5432/memory_db
EXTRACTOR_MODE=rule  # 真实环境请改为 'llm'
OPENAI_API_KEY=sk-proj-xxx
```
**3. 运行服务**
```bash
python main.py
```

## 🔌 高阶 API 调用示例
发送对话，系统会非阻塞地将其放入队列，进行大模型抽取计算：
```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/sessions/session-123/messages' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "peer_id": "user_wang",
  "content": "I prefer using Python for machine learning tasks."
}'
```

在 Agent 回复用户前，先向引擎查询相关的用户特征：
```bash
curl -X 'GET' \
  'http://127.0.0.1:8000/memories?observer=system&observed=user_wang&query=Python&top_k=5' \
  -H 'accept: application/json'
```
*返回体示例 (高亮展示了系统整合后的 deductive 事实)：*
```json
[
  {
    "score": 0.95,
    "content": "user_wang 高度依赖 Python 进行机器学习工程",
    "level": "deductive"
  }
]
```

## 📄 开源协议
本项目采用 MIT 协议开源 - 查看 [LICENSE](LICENSE) 了解更多细节。
