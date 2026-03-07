# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Conversational product search API built with FastAPI and LangGraph. Users send natural language queries (e.g., "show me Nike running shoes under 2000"), and a LangGraph agent extracts filters, performs vector search against Qdrant, reranks results with Claude, and returns structured product results. Supports multi-tenancy and session-based filter accumulation.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server (port 8000 by default, configurable via PORT env var)
python main.py

# Ingest sample product catalog into Qdrant (uses in-memory Qdrant if no cloud credentials)
python scripts/ingest_catalog.py [tenant_id]  # defaults to "retailer_abc"
```

## Environment Setup

Copy `.env.example` to `.env` and fill in:
- `ANTHROPIC_API_KEY` - required for Claude LLM calls (filter extraction + reranking)
- `QDRANT_URL` / `QDRANT_API_KEY` - optional; falls back to in-memory Qdrant for local dev
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` - optional observability; disabled if not set

## Architecture

**LangGraph Agent Pipeline** (`agent/`): Linear graph with 7 nodes executed sequentially:
`load_session → extract_filters → merge_filters → hybrid_search → rerank → save_session → build_response`

- `extract_filters` and `rerank` are the two LLM-calling nodes (Claude via direct Anthropic SDK, model: `claude-sonnet-4-20250514`)
- State flows through `SearchState` TypedDict defined in `agent/state.py`

**Services** (`services/`): All services use singleton pattern via `get_*()` factory functions.
- `QdrantService` - vector DB operations; collections are per-tenant (`{tenant_id}_products`); embeddings via `all-MiniLM-L6-v2` (384 dims)
- `SessionStore` - in-memory session store with TTL; sessions accumulate filters across turns so conversational refinement works
- `EmbeddingService` - sentence-transformers wrapper for encoding queries and product text

**API Routes** (`routers/`):
- `POST /api/v1/search` - main search endpoint, accepts `SearchRequest` (tenant_id, session_id, message)
- `POST /api/v1/ingest/product` - single product ingest
- `POST /api/v1/ingest/products/bulk` - bulk ingest (max 500)
- `GET /api/v1/ingest/collection/{tenant_id}` - collection info
- `DELETE /api/v1/ingest/product/{tenant_id}/{sku}` - delete product

**Observability** (`observability/`): Optional Langfuse tracing wraps each agent node with spans and tracks LLM generations.

## Key Design Decisions

- **Multi-tenancy**: Each tenant gets its own Qdrant collection (`{tenant_id}_products`)
- **Session-based filters**: Filters persist across turns within a session, enabling conversational refinement ("show me Nike shoes" → "under 2000" → "in size 10")
- **Hybrid search**: Combines vector similarity (semantic) with Qdrant metadata filters (category, brand, price range, size, color, attributes)
- **Product point IDs**: Qdrant point IDs are derived from `abs(hash(sku)) % (10**18)`
- **Payload values are lowercased** on ingest for consistent filter matching
- **Prices are in INR** (Indian Rupees) based on sample catalog
