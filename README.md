# 🧠 SynapseEngine (formerly Mini Memory Engine)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)

*Read this in other languages: [English](README.md), [简体中文](README_zh.md).*

---

**SynapseEngine** is a lightweight, industrial-grade AI memory system inspired by [Honcho](https://github.com/plastic-labs/honcho). It serves as an independent background service that provides stateful, long-term memory for your Agents and LLM applications via standard RESTful APIs.

It's not just a chat logger—it's a system capable of "self-evolution", automatically extracting facts, summarizing contexts, resolving conflicts, and building multi-perspective user profiles.

## ✨ Features
- 🚀 **FastAPI Backend**: Ready-to-use, scalable HTTP API layer for your multi-agent systems.
- 💾 **PostgreSQL & Vector Ready**: Persistent storage via SQLAlchemy with a designed abstraction for vector indexing.
- 🧬 **Memory Evolution**: Implements a hierarchical memory model (`explicit` -> `deductive` -> `inductive` -> `insight`).
- 🔄 **Async Processing Loop**: Non-blocking message ingestion; memory extraction and consolidation happen entirely in the background.
- 🛠️ **Modular Architecture**: Clean, domain-driven design, ready for production adaptation.

## 🧠 Core Philosophy & Concepts
Our design eschews heavyweight SDKs in favor of a pure API engine that integrates seamlessly into any tech stack.
- **Message**: The atomic unit of conversation. Automatically triggers background extraction.
- **Observation**: Facts extracted from messages. Categorized by evolutionary levels (`explicit`, `deductive`, `inductive`, `insight`).
- **Summary**: Auto-generated contextual compressions created every N messages.
- **Recursive Dream**: A background process that clusters lower-level observations into higher-level insights.

## 📦 System Architecture

```mermaid
graph TD
    Client[Client / Agent] -->|POST Message| API[FastAPI /sessions/*/messages]
    API --> DB[(PostgreSQL)]
    API -.->|Enqueue Task| TaskQueue[Background Task Queue]
    
    subgraph Async Worker Loop
        TaskQueue --> Extractor[LLM Extractor]
        Extractor -->|Generates| Obs[Observations]
        Obs --> Matcher[Semantic Matcher]
        Matcher -->|Merge / Resolve| Consolidator[Consolidator]
    end
    
    Consolidator --> DB
    Consolidator --> VectorDB[(Vector DB / Index)]
    
    Client -->|GET /memories| SearchAPI[FastAPI /memories]
    SearchAPI --> VectorDB
```

## 🚀 Quick Start
**1. Installation**
```bash
git clone https://github.com/yourusername/SynapseEngine.git
cd SynapseEngine
pip install -r requirements.txt
```
**2. Configuration**
```bash
cp .env.example .env
```
Edit the `.env` file to set your `DATABASE_URL` and `OPENAI_API_KEY`:
```env
DATABASE_URL=postgresql://user:password@localhost:5432/memory_db
EXTRACTOR_MODE=rule  # Use 'llm' for real AI extraction
OPENAI_API_KEY=sk-proj-xxx
```
**3. Run the Server**
```bash
python main.py
```

## 🔌 Advanced API Usage
Store a message and trigger the background extraction asynchronously:
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

Query the generated observations using a semantic search:
```bash
curl -X 'GET' \
  'http://127.0.0.1:8000/memories?observer=system&observed=user_wang&query=Python&top_k=5' \
  -H 'accept: application/json'
```
*Response Example:*
```json
[
  {
    "score": 0.95,
    "content": "user_wang heavily relies on Python for ML engineering.",
    "level": "deductive"
  }
]
```

## 📄 License
MIT License. See [LICENSE](LICENSE).
