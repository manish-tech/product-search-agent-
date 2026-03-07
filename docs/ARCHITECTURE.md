# Product Search Agent — Architecture & Technical Deep Dive

## What Does This Project Do?

This is a **conversational product search API** for e-commerce. Instead of rigid keyword search, users can type natural language queries like:

- *"Nike running shoes under 2000"*
- *"something warm for a trek under 1500"*
- *"show me waterproof trekking shoes in size 10"*

The system understands intent, extracts filters, searches a product catalog, and returns ranked results — all through a REST API.

**Key feature:** It remembers context across turns. After searching "Nike running shoes", the user can say "under 2000" and the system combines both queries.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Client (Postman / Frontend)              │
│                                                                  │
│   POST /api/v1/search                                            │
│   { tenant_id, session_id, message }                             │
└──────────────────┬───────────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                         FastAPI Server                           │
│                                                                  │
│   ┌─────────────┐    ┌──────────────┐    ┌───────────────────┐  │
│   │ Search Router│    │ Ingest Router│    │ Health / Root     │  │
│   └──────┬──────┘    └──────────────┘    └───────────────────┘  │
│          │                                                       │
│          ▼                                                       │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │              LangGraph Agent (7-node pipeline)            │  │
│   │                                                          │  │
│   │  load_session → extract_filters → merge_filters →        │  │
│   │  hybrid_search → rerank → save_session → build_response  │  │
│   └──────────────────────────────────────────────────────────┘  │
│          │              │                    │                    │
│          ▼              ▼                    ▼                    │
│   ┌───────────┐  ┌───────────┐      ┌─────────────┐            │
│   │  Session   │  │   Groq    │      │   Qdrant    │            │
│   │  Store     │  │   LLM     │      │  (in-memory)│            │
│   │(in-memory) │  │(llama-3.3)│      │  + Embedder │            │
│   └───────────┘  └───────────┘      └─────────────┘            │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │              Langfuse (observability / tracing)            │  │
│   └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Why These Technology Choices?

### Why LangGraph?

The search pipeline has **7 sequential steps** that share state. LangGraph gives us:

- **Typed state** (`SearchState` TypedDict) — every node reads/writes to the same state object
- **Visual pipeline** — the flow is explicit: `load_session → extract_filters → merge_filters → ...`
- **Easy to extend** — adding a new node (e.g., spell check, caching) is just adding one function and one edge

**Alternative considered:** Plain function calls. But LangGraph makes the flow declarative and easier to debug.

### Why Groq + Llama 3.3?

- **Free tier** — no cost for MVP/development
- **Fast inference** — Groq's LPU hardware gives sub-second LLM responses
- **Good enough** — Llama 3.3 70B handles JSON extraction and reranking well

The LLM is called in only **2 places**: filter extraction and result reranking.

### Why Qdrant (in-memory)?

- **Vector search** — finds semantically similar products ("something warm for trek" → jackets, fleece)
- **Metadata filtering** — combines vector similarity with hard filters (price range, brand, size)
- **In-memory mode** — zero infrastructure for MVP. Data is loaded on startup from the catalog script

**Trade-off:** Data is lost on restart. For production with persistent data, switch to Qdrant Cloud (free 1GB tier).

### Why HuggingFace Inference API (all-MiniLM-L6-v2)?

- **No local model needed** — embeddings are computed via HuggingFace's free API
- **Low memory** — app uses ~100 MB RAM instead of ~430 MB with local sentence-transformers
- **384-dimensional vectors** — small and fast
- **Good quality** — despite its size, it captures semantic meaning well enough for product search
- **Free tier** — requires a free HF token, 1,000 requests/day

### Why Langfuse?

- **Traces every search request** end-to-end
- **Shows LLM calls** — what prompt was sent, what the LLM returned, token count, latency
- **Free cloud tier** — 50k observations/month
- **Debugging** — when search returns bad results, you can see exactly which node went wrong

---

## The 7-Node Agent Pipeline — Explained

### Node 1: `load_session`

```
Input:  session_id, tenant_id
Output: session object (filters from previous turns)
```

**What:** Fetches the session from the in-memory store. If it's a new session_id, creates one.

**Why:** Sessions let users refine searches across turns. Without this, every query starts from scratch.

**Example:**
```
Turn 1: "Nike running shoes"     → session.filters = {brand: "Nike", category: "running shoes"}
Turn 2: "under 2000"             → loads existing filters, will merge new price filter
```

### Node 2: `extract_filters`

```
Input:  user message + session filters
Output: structured JSON filters
```

**What:** Sends the user's message to the LLM (Groq/Llama 3.3) with a system prompt that says "parse this into structured JSON." The LLM returns:

```json
{
  "category": "running shoes",
  "brand": "Nike",
  "price_max": 2000,
  "attributes": ["wide fit"],
  "semantic_query": "Nike running shoes wide fit"
}
```

**Why:** Natural language is messy. "Nike shoes under 2k for wide feet" contains a brand filter, price filter, attribute filter, and semantic meaning — all mixed together. The LLM separates these into structured fields that Qdrant can filter on.

**Key design decisions:**
- The prompt includes the **exact list of valid categories and brands** from the catalog. This prevents the LLM from returning "shoes" instead of "running shoes".
- The prompt explains price direction: "under X" = price_max, "above X" = price_min.
- `semantic_query` is a cleaned version of the query for vector search (stripped of filter keywords).

### Node 3: `merge_filters`

```
Input:  extracted filters + session filters
Output: merged filters
```

**What:** Combines new filters with existing session filters. New values override old ones.

**Why:** This is what makes multi-turn work.

```
Session filters:  {brand: "Nike", category: "running shoes"}
New extraction:   {price_max: 2000}
Merged result:    {brand: "Nike", category: "running shoes", price_max: 2000}
```

**Edge case handled:** If merge creates an impossible price range (price_min > price_max), it drops the conflicting old value.

### Node 4: `hybrid_search`

```
Input:  merged filters + semantic query
Output: raw product results from Qdrant
```

**What:** This is the core search. It does TWO things simultaneously:

1. **Vector similarity search** — embeds the `semantic_query` into a 384-dim vector, finds products with similar vectors (cosine similarity)
2. **Metadata filtering** — applies hard filters on category, brand, price range, size, color, attributes

```python
results = qdrant.query_points(
    collection_name="retailer_abc_products",
    query=query_vector,          # semantic similarity
    query_filter=qdrant_filter,  # hard metadata filters
    limit=10
)
```

**Why hybrid?** Pure keyword search misses intent ("something warm" won't match "insulated jacket"). Pure vector search ignores hard constraints ("under 2000" isn't semantic). Hybrid combines both.

**How metadata filters work in Qdrant:**

```python
Filter(
    must=[
        FieldCondition(key="brand", match=MatchValue(value="nike")),
        FieldCondition(key="price", range=Range(lte=2000)),
    ],
    must_not=[
        FieldCondition(key="brand", match=MatchValue(value="adidas")),  # exclude_brands
    ]
)
```

### Node 5: `rerank`

```
Input:  raw results (top 10) + user intent
Output: reranked results
```

**What:** Sends the top-K results back to the LLM and asks: "Given the user's intent, reorder these by relevance." The LLM returns SKUs in order.

**Why:** Vector similarity isn't perfect. A shoe that's semantically similar might not be the best match for the user's actual intent. The LLM understands nuance better.

**Optimization:** Skips reranking if there are ≤3 results (not worth the LLM call).

### Node 6: `save_session`

```
Input:  merged filters + final result SKUs
Output: (none — side effect: updates session store)
```

**What:** Saves the current merged filters and result SKUs back to the session.

**Why:** So the next turn can build on these filters.

### Node 7: `build_response`

```
Input:  final results + merged filters
Output: formatted response with reasons + follow-up hint
```

**What:** Formats each result with a human-readable `reason` ("Matches Nike brand, under ₹2000, in running shoes") and generates a `follow_up_hint` ("Would you like to filter by size or color?").

**Why:** Explainability. Users want to know *why* a product was returned. The follow-up hint guides the conversation.

---

## Multi-Tenancy

Each tenant (retailer) gets its own Qdrant collection:

```
tenant_id = "retailer_abc"  →  collection = "retailer_abc_products"
tenant_id = "retailer_xyz"  →  collection = "retailer_xyz_products"
```

**Why:** Complete data isolation. Retailer A's products never leak into Retailer B's search results. No row-level filtering needed — it's physical separation at the collection level.

---

## Session Design

### Why Sessions?

Without sessions, every query is independent:
- User: "Nike running shoes" → results
- User: "under 2000" → searches for "under 2000" with no context → useless results

With sessions:
- User: "Nike running shoes" → results, saves `{brand: Nike, category: running shoes}`
- User: "under 2000" → merges to `{brand: Nike, category: running shoes, price_max: 2000}` → filtered results

### How It Works

```
Client generates UUID → sends as session_id → server creates/loads session
                                              → session stores filter state
                                              → session expires after 30 min inactivity
```

**Design choice:** The client generates the session_id (UUID v4), not the server. This means:
- No "create session" API call needed
- Client controls session lifecycle
- Stateless from the server's perspective (except the in-memory store)

**Storage:** Simple Python dict with TTL. No Redis, no database.

```python
{
    "session_id_123": Session(
        filters={"brand": "Nike", "price_max": 2000},
        last_result_ids=["NK-RUN-001", "NK-RUN-002"],
        last_active=datetime(...)
    )
}
```

---

## Embedding & Vector Search — How It Works

### Product Ingestion

When a product is ingested:

1. Concatenate searchable text: `"{name} {category} {attributes} {description}"`
2. Run through sentence-transformers → 384-dim float vector
3. Store vector + metadata payload in Qdrant

```
"Nike Air Zoom Wide Runner running shoes wide fit cushioned lightweight ..."
                    ↓ sentence-transformers
           [0.023, -0.119, 0.445, ..., 0.087]  (384 floats)
                    ↓
           Qdrant point with payload {sku, name, price, brand, ...}
```

### Search Query

When a user searches:

1. LLM extracts `semantic_query` from user message
2. Embed that query → 384-dim vector
3. Qdrant finds products whose vectors are closest (cosine similarity)
4. Metadata filters narrow results further

**Why cosine similarity?** It measures the angle between vectors, not magnitude. "running shoes" and "shoes for running" will have similar directions even if the exact words differ.

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/search` | Main search — natural language query |
| `POST` | `/api/v1/ingest/product` | Ingest single product |
| `POST` | `/api/v1/ingest/products/bulk` | Ingest up to 500 products |
| `GET` | `/api/v1/ingest/collection/{tenant_id}` | Collection info (point count) |
| `DELETE` | `/api/v1/ingest/product/{tenant_id}/{sku}` | Delete a product |
| `GET` | `/health` | Health check |
| `GET` | `/` | API info |

---

## Observability with Langfuse

Every search request creates a **trace** with nested **spans**:

```
Trace: product-search (session_id, tenant_id)
├── Span: load_session
│   └── output: {session_filters: {...}}
├── Span: extract_filters
│   └── Generation: groq-filter-extraction
│       ├── model: llama-3.3-70b-versatile
│       ├── input: user prompt
│       ├── output: extracted JSON
│       └── usage: {input_tokens: 245, output_tokens: 89}
├── Span: merge_filters
│   └── output: {merged_filters: {...}}
├── Span: hybrid_search
│   └── output: {query, filters_used, num_results}
├── Span: rerank
│   └── Generation: groq-rerank
│       ├── input: products + user intent
│       └── output: ranked SKU list
├── Span: save_session
└── Span: build_response
    └── output: {num_results, follow_up_hint}
```

**What you can debug from Langfuse dashboard:**
- Why did the LLM extract wrong filters? → Check the `extract_filters` generation
- Why were results irrelevant? → Check `hybrid_search` span (what filters were applied?)
- How long did each step take? → Span durations
- How many tokens are being used? → Generation usage stats

---

## Data Flow Example

**User sends:** `"waterproof trekking shoes under 1500"`

```
1. load_session
   → No existing session → creates empty one
   → session.filters = {}

2. extract_filters (LLM call)
   → Input: "waterproof trekking shoes under 1500"
   → Output: {
       category: "trekking shoes",
       price_max: 1500,
       attributes: ["waterproof"],
       semantic_query: "waterproof trekking shoes"
     }

3. merge_filters
   → Session filters: {} (empty)
   → Merged: {category: "trekking shoes", price_max: 1500, attributes: ["waterproof"]}

4. hybrid_search
   → Embeds "waterproof trekking shoes" → [0.12, -0.34, ...]
   → Qdrant filter: category="trekking shoes" AND price<=1500 AND attributes HAS "waterproof"
   → Returns: [WL-TRK-001 (₹1499, score 0.91), DK-TRK-001 (₹999, score 0.76), ...]

5. rerank (LLM call)
   → Reorders by relevance to "waterproof trekking shoes under 1500"
   → WL-TRK-001 stays first (waterproof, ₹1499, exact match)

6. save_session
   → Saves filters + result SKUs to session

7. build_response
   → Formats results with reasons
   → Generates hint: "Would you like to filter by size or color?"
```

**Next turn:** `"in size 10"`

```
1. load_session → filters = {category: "trekking shoes", price_max: 1500, attributes: ["waterproof"]}
2. extract_filters → {size: "10"}
3. merge_filters → {category: "trekking shoes", price_max: 1500, attributes: ["waterproof"], size: "10"}
4. hybrid_search → narrower results with size filter
5-7. ... same flow
```

---

## Project Structure

```
product-search-agent/
├── main.py                     # FastAPI app, lifespan (startup/shutdown), CORS
├── agent/
│   ├── graph.py                # LangGraph StateGraph — defines the 7-node pipeline
│   ├── nodes.py                # All 7 node functions + LLM prompts
│   └── state.py                # SearchState TypedDict (shared state schema)
├── services/
│   ├── embedder.py             # sentence-transformers wrapper (singleton)
│   ├── qdrant_service.py       # Qdrant CRUD + hybrid search (singleton)
│   └── session_store.py        # In-memory session dict with TTL (singleton)
├── models/
│   └── schemas.py              # Pydantic models for all request/response types
├── routers/
│   ├── search.py               # POST /api/v1/search
│   └── ingest.py               # Ingest + delete + collection info endpoints
├── observability/
│   └── langfuse_client.py      # Langfuse v3 trace/span/generation wrappers
├── scripts/
│   └── ingest_catalog.py       # Generates 499 products, ingests via API or direct
├── render.yaml                 # Render.com deployment config
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Singleton Pattern

All services use the singleton pattern:

```python
_embedder = None

def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingService()  # expensive to create (loads ML model)
    return _embedder
```

**Why:** The embedding model takes seconds to load. The Qdrant client maintains a connection. Creating these per-request would be wasteful. Singletons ensure one instance shared across all requests.

---

## Known Limitations

| Limitation | Why It Exists | How to Fix |
|---|---|---|
| In-memory Qdrant (data lost on restart) | MVP simplicity | Switch to Qdrant Cloud (free tier) |
| In-memory sessions (lost on restart) | No Redis dependency | Add Redis or database-backed sessions |
| No authentication | Out of scope for MVP | Add API key middleware |
| 499 products only | Sample catalog | Ingest real catalog via bulk API |
| LLM sometimes extracts wrong filters | LLM imperfection | Better prompts, few-shot examples, validation |
| No spelling correction | Not implemented | Add a spell-check node before extract_filters |
