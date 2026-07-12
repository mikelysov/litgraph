# Litgraph

> 🚧 Under construction

Graph-augmented semantic search for academic literature

## Features

- 📄 Fetch papers from ArXiv API
- 🧠 Queue papers for embedding (deferred, async)
- 🧮 Track paper ingestion state in SQLite index
- 📦 Index embeddings into Qdrant
- 🔍 Search Qdrant with BGE-M3 embeddings
- 🤖 LLM-powered RAG answers (Gemma 3 4B)
- 🎯 Cross-encoder reranking (Jina Reranker V3)
- 🔌 MCP server for AI agent integration (Claude Desktop, etc.)
- 🧩 Merge vector + (planned) graph hits
- ✅ Type-safe, testable, modular pipeline
- ⚙️ Health checks, typed interfaces, and task runner setup
- ⚡ Models preloaded at startup for instant response

## Models

Three models loaded at server startup:

| Model | Purpose | Size |
|-------|---------|------|
| BGE-M3 | Text embeddings (1024-dim) | ~560M |
| Gemma 3 4B IT | RAG answer generation | 4.3B |
| Jina Reranker V3 | Cross-encoder reranking | 0.6B |

## Usage

### Requirements

- Python 3.12+
- Node.js 20+
- Docker + Docker Compose
- NVIDIA GPU (CUDA) for LLM/reranker

### Local dev (CPU by default)

```bash
make up-full        # Run full stack with CPU
make up-full USE_GPU=1  # Run with GPU (requires NVIDIA runtime)
```

Services:

- **API** → [http://localhost:8889/docs](http://localhost:8889/docs)
- **MCP Server** → [http://localhost:8888/mcp](http://localhost:8888/mcp) (streamable-http)
- **Qdrant UI** → [http://localhost:6333/dashboard](http://localhost:6333/dashboard)
- **Redis** → localhost:6379 (use `redis-cli`)

### Direct tasks (no Docker)

```bash
# Start FastAPI backend
cd backend && python -m uvicorn src.server:app --host 0.0.0.0 --port 8889

# Start MCP server
cd backend && python -m src.mcp_server

# Run end-to-end pipeline
poe pipeline

# Run tests
poe test
```

### Environment

```env
QDRANT_HOST=localhost
QDRANT_PORT=6333
REDIS_URL=redis://localhost:6379/0
EMBEDDING_MODEL_PATH=/path/to/bge-m3
EMBEDDING_DIM=1024
LLM_MODEL_PATH=/path/to/gemma-3-4b-it
RERANKER_MODEL_PATH=/path/to/jina-reranker-v3
MCP_PORT=8888
```

## Diagram

<details>
<summary>System architecture diagram</summary>

```mermaid
flowchart TD
    subgraph API
        A1[GET /search] --> P["run_pipeline()"]
    end

    subgraph MCP["MCP Server :8888"]
        M1[ask tool] --> S[Semantic Search]
        S --> R[Rerank via Jina V3]
        R --> L[Generate via Gemma 3]
    end

    subgraph Pipeline
        P --> F[Discover papers from ArXiv]
        F --> I[Update PaperIndex]
        I --> Q[Enqueue papers if not embedded]
        Q --> S2[Semantic Search]
        S2 --> G[Get related from GraphStore]
        G --> M[Merge vector + graph results]
        M --> R2[Return SearchResults]
    end

    subgraph Models["Models (preloaded)"]
        E1[BGE-M3 Embedder]
        E2[Gemma 3 4B LLM]
        E3[Jina Reranker V3]
    end

    subgraph Vector Store
        V1["Qdrant (hosted/local)"]
    end

    subgraph Embedding Worker
        W1["Reads Redis queue"]
        W1 --> EB[Embed papers via BGE-M3]
        EB --> V[Upsert to Qdrant]
        V --> U[Update PaperIndex status]
    end

    subgraph Graph Store
        G1["(Planned) Neo4j / in-memory graph"]
    end

    S -->|vector hits| V1
    S2 -->|vector hits| V1
    G -->|edges| G1
    G1 -->|related| G
```

</details>

Stack highlights:

- Backend: FastAPI + Pydantic + uv
- LLM/Reranker: HuggingFace Transformers (Gemma 3 + Jina V3)
- Embeddings: Sentence-Transformers (BGE-M3)
- MCP: FastMCP (streamable-http)
- Queue: Redis (Upstash or local)
- Vector DB: Qdrant
- Frontend: React + Vite + Tailwind
- Infra: Docker Compose

## Acknowledgements

Thank you to arXiv for use of its open access interoperability.

## License

MIT
