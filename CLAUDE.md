# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Conversational product search API built with FastAPI and LangGraph. Users send natural language queries (e.g., "show me Nike running shoes under 2000"), and a LangGraph agent extracts filters, performs vector search against Qdrant, reranks results with Groq LLM, and returns structured product results. Supports multi-tenancy and session-based filter accumulation.

**Deployed at:** https://product-search-agent.onrender.com

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server (port 8000 by default, configurable via PORT env var)
python main.py

# Server auto-ingests 50 sample products on startup (in-memory Qdrant)
# No separate ingest step needed
```

## Environment Setup

Copy `.env.example` to `.env` and fill in:
- `GROQ_API_KEY` - required for Groq LLM calls (filter extraction + reranking)
- `HF_TOKEN` - required for HuggingFace Inference API (embeddings)
- `QDRANT_URL` / `QDRANT_API_KEY` - optional; falls back to in-memory Qdrant for local dev
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` - optional observability via Langfuse Cloud

## Architecture

**LangGraph Agent Pipeline** (`agent/`): Linear graph with 7 nodes executed sequentially:
`load_session → extract_filters → merge_filters → hybrid_search → rerank → save_session → build_response`

- `extract_filters` and `rerank` are the two LLM-calling nodes (Groq API, model: `llama-3.3-70b-versatile`)
- State flows through `SearchState` TypedDict defined in `agent/state.py`

**Services** (`services/`): All services use singleton pattern via `get_*()` factory functions.
- `QdrantService` - vector DB operations; collections are per-tenant (`{tenant_id}_products`); supports batch upsert
- `SessionStore` - in-memory session store with TTL; sessions accumulate filters across turns
- `EmbeddingService` - HuggingFace Inference API wrapper using `all-MiniLM-L6-v2` (384 dims); no local model needed

**API Routes** (`routers/`): Registered lazily in background thread after startup init completes.
- `POST /api/v1/search` - main search endpoint, accepts `SearchRequest` (tenant_id, session_id, message)
- `POST /api/v1/ingest/product` - single product ingest
- `POST /api/v1/ingest/products/bulk` - bulk ingest (max 500)
- `GET /api/v1/ingest/collection/{tenant_id}` - collection info
- `DELETE /api/v1/ingest/product/{tenant_id}/{sku}` - delete product
- `GET /health` - always returns 200
- `GET /ready` - returns 503 during init, 200 when ready

**Observability** (`observability/`): Langfuse v3 tracing wraps each agent node with spans and tracks LLM generations.

## Key Design Decisions

- **Lazy imports**: All heavy dependencies (langgraph, groq, qdrant, huggingface_hub) are imported lazily to ensure fast port binding on Render
- **Background init**: Embedding service, Qdrant, and product ingestion run in a background thread so the server starts instantly
- **Multi-tenancy**: Each tenant gets its own Qdrant collection (`{tenant_id}_products`)
- **Session-based filters**: Filters persist across turns within a session, enabling conversational refinement
- **Hybrid search**: Combines vector similarity (semantic) with Qdrant metadata filters (category, brand, price range, size, color, attributes)
- **Product point IDs**: Qdrant point IDs are derived from `hashlib.sha256(sku)` (deterministic, collision-resistant)
- **Payload values are lowercased** on ingest for consistent filter matching
- **Prices are in INR** (Indian Rupees) based on sample catalog

## Deployment

Deployed on Render.com free tier. Config in `render.yaml`. Required env vars in Render dashboard:
- `GROQ_API_KEY`, `HF_TOKEN`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
