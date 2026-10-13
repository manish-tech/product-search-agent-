# Conversational Product Search Agent

Natural-language product search for e-commerce: a LangGraph agent that extracts filters with an LLM, runs hybrid (vector + metadata) search in Qdrant, reranks results, and remembers context across turns.

```text
You:   "nike running shoes"
Agent: filters → {brand: nike, category: running shoes}

You:   "under 2000"
Agent: filters → {brand: nike, category: running shoes, price_max: 2000}

You:   "in size 10"
Agent: filters → {brand: nike, category: running shoes, price_max: 2000, size: 10}
```

Keyword search fails on queries like *"something warm for a trek under 1500"*. This agent separates the hard constraints (price, brand, size) from the semantic intent ("warm", "trek") and handles each with the right tool.

**Live demo:** https://product-search-agent.onrender.com (free tier, so the first request may take ~30s to wake up)

---

## How it works

A 7-node LangGraph pipeline with typed shared state:

```text
load_session → extract_filters → merge_filters → hybrid_search → rerank → save_session → build_response
                    (LLM)                          (Qdrant)       (LLM)
```

| Node | What it does |
|---|---|
| `load_session` | Loads filters accumulated in earlier turns (client-generated session id, 30 min TTL) |
| `extract_filters` | Groq · Llama 3.3 70B turns the message into structured JSON: category, brand, price range, size, color, attributes, and a cleaned `semantic_query` |
| `merge_filters` | Merges new filters with session filters; resolves conflicts such as `price_min > price_max` |
| `hybrid_search` | Embeds the semantic query (`all-MiniLM-L6-v2`, 384-d) and runs Qdrant vector search **with** metadata filters in one query |
| `rerank` | LLM reorders the top-K by intent; skipped when ≤3 results |
| `save_session` | Persists merged filters for the next turn |
| `build_response` | Adds a human-readable match reason per result and a follow-up hint |

Full write-up with design trade-offs: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Design decisions

- **Hybrid search, not pure vector.** Vectors capture intent; "under 2000" is a hard constraint, not a semantic one.
- **Grounded extraction.** The prompt includes the catalog's valid categories and brands, so the LLM can't invent a category that matches nothing.
- **Multi-tenant by collection.** Each retailer gets its own Qdrant collection (`{tenant_id}_products`), so tenant data is physically isolated.
- **Observability first.** Every node is a Langfuse span and every LLM call is a tracked generation, so a bad result can be traced to the step that caused it.
- **Fast cold starts.** Lazy imports and background initialization let the server bind its port immediately on Render's free tier; `/ready` reports when ingestion is done.

## Tech stack

FastAPI · LangGraph · Groq (Llama 3.3 70B) · Qdrant · HuggingFace Inference API · Langfuse · Render

## Run locally

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add GROQ_API_KEY and HF_TOKEN (Qdrant + Langfuse are optional)
python main.py              # http://localhost:8000, auto-ingests a sample catalog
```

Try it:

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "retailer_abc", "session_id": "demo-1", "message": "waterproof trekking shoes under 1500"}'
```

A Postman collection with every endpoint is included: `Product_Search_Agent.postman_collection.json`.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/search` | Conversational search |
| `POST` | `/api/v1/ingest/product` | Ingest one product |
| `POST` | `/api/v1/ingest/products/bulk` | Ingest up to 500 products |
| `GET` | `/api/v1/ingest/collection/{tenant_id}` | Collection info |
| `DELETE` | `/api/v1/ingest/product/{tenant_id}/{sku}` | Delete a product |
| `GET` | `/health`, `/ready` | Liveness / readiness |

## Limitations & next steps

- In-memory Qdrant and sessions are reset on restart. Next steps: Qdrant Cloud and Redis.
- No auth yet. Next step: API-key middleware.
- Filter extraction can still miss. Next steps: few-shot examples, schema validation, and an eval set of query → expected-filters pairs.
