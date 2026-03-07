import json
import os
from typing import Any

from groq import Groq

from agent.state import SearchState
from services.session_store import get_session_store
from services.qdrant_service import get_qdrant_service
from models.schemas import ExtractedFilters


# Model to use
MODEL = "llama-3.3-70b-versatile"

# Lazy Groq client
_client = None


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq()
    return _client


def load_session(state: SearchState) -> dict:
    """Load or create session from the session store."""
    session_store = get_session_store()
    session = session_store.get_or_create(
        session_id=state["session_id"],
        tenant_id=state["tenant_id"]
    )

    # Start span if trace exists
    trace = state.get("trace")
    if trace:
        span = trace.span(name="load_session")
        span.end(output={"session_filters": session.filters})

    return {
        "session": {
            "session_id": session.session_id,
            "tenant_id": session.tenant_id,
            "filters": session.filters,
            "last_result_ids": session.last_result_ids
        }
    }


def extract_filters(state: SearchState) -> dict:
    """Extract structured filters from user message using Groq LLM."""
    session_filters = state["session"].get("filters", {})
    user_message = state["user_message"]

    system_prompt = """You are a product search query parser for an e-commerce platform.
Extract structured filters from the user's message and existing session context.
Always respond with valid JSON only. No explanation, no markdown.

JSON schema:
{
  "category": string | null,
  "brand": string | null,
  "price_min": number | null,
  "price_max": number | null,
  "size": string | null,
  "color": string | null,
  "attributes": [string],
  "exclude_brands": [string],
  "semantic_query": string
}

Available categories (use EXACTLY these values):
- running shoes
- trekking shoes
- casual sneakers
- jackets
- backpacks
- sports wear
- formal shoes
- sandals
- gym equipment
- watches

Available brands:
Nike, Adidas, Puma, New Balance, Asics, Woodland, Decathlon, Salomon, Merrell,
Converse, Vans, Clarks, Hush Puppies, Red Tape, Louis Philippe, Bata, Boldfit,
Cult Sport, Casio, Titan, Fastrack, Noise, Boat, Columbia, The North Face,
Under Armour, Reebok, Wildcraft

Rules:
- Extract explicit filters mentioned in the query
- category MUST be one of the available categories listed above, or null if unclear
- brand MUST be one of the available brands listed above, or null if not mentioned
- semantic_query should be a cleaned version of the query suitable for semantic search
- Preserve relevant context from session filters
- If user says "clear filters" or "start over", return empty filters
- Price values should be numbers only, no currency symbols
- "under X" or "below X" or "less than X" means price_max = X
- "above X" or "more than X" or "over X" means price_min = X
- Attributes are features like "wide fit", "waterproof", "lightweight", etc."""

    user_prompt = f"""Current session filters: {json.dumps(session_filters)}
New message: {user_message}"""

    trace = state.get("trace")
    span = None
    if trace:
        span = trace.span(name="extract_filters")

    try:
        response = get_client().chat.completions.create(
            model=MODEL,
            max_tokens=500,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )

        response_text = response.choices[0].message.content.strip()

        # Try to parse JSON from response
        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        extracted = json.loads(response_text)

        # Log to Langfuse
        if span:
            span.generation(
                name="groq-filter-extraction",
                model=MODEL,
                input=user_prompt,
                output=response_text,
                usage={
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens
                }
            )
            span.end()

        return {"extracted_filters": extracted}

    except Exception as e:
        if span:
            span.end(status_message=str(e), level="ERROR")

        # Return minimal filters on error
        return {
            "extracted_filters": {
                "semantic_query": user_message,
                "attributes": []
            },
            "error": f"Filter extraction error: {str(e)}"
        }


def merge_filters(state: SearchState) -> dict:
    """Merge extracted filters with session filters."""
    session_filters = state["session"].get("filters", {})
    extracted = state["extracted_filters"]

    trace = state.get("trace")
    if trace:
        span = trace.span(name="merge_filters")

    # Start with session filters
    merged = session_filters.copy()

    # Merge in new filters (new values override old)
    filter_keys = ["category", "brand", "price_min", "price_max", "size", "color"]

    for key in filter_keys:
        if extracted.get(key) is not None:
            merged[key] = extracted[key]

    # Merge attributes (combine lists, remove duplicates)
    existing_attrs = set(merged.get("attributes", []))
    new_attrs = set(extracted.get("attributes", []))
    merged["attributes"] = list(existing_attrs | new_attrs)

    # Handle exclude_brands
    existing_excludes = set(merged.get("exclude_brands", []))
    new_excludes = set(extracted.get("exclude_brands", []))
    merged["exclude_brands"] = list(existing_excludes | new_excludes)

    # Fix impossible price ranges
    price_min = merged.get("price_min")
    price_max = merged.get("price_max")
    if price_min is not None and price_max is not None and price_min > price_max:
        # New query likely intended to replace the range, not combine
        # Keep whichever was set in the current extraction
        if extracted.get("price_max") is not None:
            merged.pop("price_min", None)
        elif extracted.get("price_min") is not None:
            merged.pop("price_max", None)

    if trace:
        span.end(output={"merged_filters": merged})

    return {"merged_filters": merged}


def hybrid_search(state: SearchState) -> dict:
    """Perform hybrid search using Qdrant."""
    qdrant = get_qdrant_service()

    tenant_id = state["tenant_id"]
    merged_filters = state["merged_filters"]
    semantic_query = state["extracted_filters"].get("semantic_query", state["user_message"])

    top_k = int(os.getenv("TOP_K_RESULTS", "10"))

    trace = state.get("trace")
    span = None
    if trace:
        span = trace.span(name="hybrid_search")

    try:
        results = qdrant.search(
            tenant_id=tenant_id,
            query=semantic_query,
            filters=merged_filters,
            limit=top_k
        )

        if span:
            span.end(output={
                "query": semantic_query,
                "filters_used": merged_filters,
                "num_results": len(results)
            })

        return {"raw_results": results}

    except Exception as e:
        if span:
            span.end(status_message=str(e), level="ERROR")

        return {
            "raw_results": [],
            "error": f"Search error: {str(e)}"
        }


def rerank_results(state: SearchState) -> dict:
    """Rerank results using Groq LLM for better relevance."""
    raw_results = state["raw_results"]
    user_message = state["user_message"]
    merged_filters = state["merged_filters"]

    # If no results or few results, skip reranking
    if len(raw_results) <= 3:
        return {"final_results": raw_results}

    trace = state.get("trace")
    span = None
    if trace:
        span = trace.span(name="rerank")

    system_prompt = """You are a product search reranker.
Given the user's intent and a list of products, rerank them by relevance.
Return only a JSON array of SKUs in order of relevance (most relevant first).
No explanation, just the JSON array."""

    # Prepare product summaries for reranking
    products_for_rerank = []
    for p in raw_results:
        products_for_rerank.append({
            "sku": p["sku"],
            "name": p["name"],
            "price": p["price"],
            "brand": p.get("brand", ""),
            "category": p.get("category", ""),
            "attributes": p.get("attributes", [])
        })

    user_prompt = f"""User intent: {user_message}
Active filters: {json.dumps(merged_filters)}
Products: {json.dumps(products_for_rerank)}"""

    try:
        response = get_client().chat.completions.create(
            model=MODEL,
            max_tokens=300,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )

        response_text = response.choices[0].message.content.strip()

        # Parse JSON array
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        ranked_skus = json.loads(response_text)

        # Log to Langfuse
        if span:
            span.generation(
                name="groq-rerank",
                model=MODEL,
                input=user_prompt,
                output=response_text,
                usage={
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens
                }
            )
            span.end()

        # Reorder results based on ranked SKUs
        sku_to_result = {r["sku"]: r for r in raw_results}
        reranked = []
        for sku in ranked_skus:
            if sku in sku_to_result:
                reranked.append(sku_to_result[sku])

        # Add any results that weren't in the ranked list
        ranked_set = set(ranked_skus)
        for r in raw_results:
            if r["sku"] not in ranked_set:
                reranked.append(r)

        return {"final_results": reranked}

    except Exception as e:
        if span:
            span.end(status_message=str(e), level="ERROR")

        # On error, return original order
        return {"final_results": raw_results}


def save_session(state: SearchState) -> dict:
    """Save updated session state."""
    session_store = get_session_store()

    session = session_store.get(state["session_id"])
    if session:
        # Update filters
        session.filters = state["merged_filters"]

        # Update last result IDs
        session.last_result_ids = [r["sku"] for r in state.get("final_results", [])]

        session_store.save(session)

    trace = state.get("trace")
    if trace:
        span = trace.span(name="save_session")
        span.end(output={"saved_filters": state["merged_filters"]})

    return {}


def build_response(state: SearchState) -> dict:
    """Build the final response with results and follow-up hint."""
    final_results = state.get("final_results", [])
    merged_filters = state.get("merged_filters", {})
    user_message = state["user_message"]

    trace = state.get("trace")
    span = None
    if trace:
        span = trace.span(name="build_response")

    # Generate follow-up hint based on results and filters
    follow_up_hint = generate_follow_up_hint(final_results, merged_filters)

    # Format results with reasons
    formatted_results = []
    for r in final_results:
        reason = generate_match_reason(r, merged_filters)
        formatted_results.append({
            "sku": r["sku"],
            "name": r["name"],
            "price": r["price"],
            "score": round(r.get("score", 0), 2),
            "reason": reason
        })

    # Create interpreted filters for response
    interpreted = {
        "category": merged_filters.get("category"),
        "brand": merged_filters.get("brand"),
        "price_min": merged_filters.get("price_min"),
        "price_max": merged_filters.get("price_max"),
        "size": merged_filters.get("size"),
        "color": merged_filters.get("color"),
        "attributes": merged_filters.get("attributes", [])
    }

    if span:
        span.end(output={
            "num_results": len(formatted_results),
            "follow_up_hint": follow_up_hint
        })

    return {
        "final_results": formatted_results,
        "follow_up_hint": follow_up_hint,
        "interpreted_filters": interpreted
    }


def generate_follow_up_hint(results: list, filters: dict) -> str:
    """Generate a helpful follow-up suggestion."""
    if not results:
        return "Try broadening your search or removing some filters."

    suggestions = []

    if not filters.get("size"):
        suggestions.append("filter by size")
    if not filters.get("color"):
        suggestions.append("filter by color")
    if not filters.get("price_max") and not filters.get("price_min"):
        suggestions.append("set a price range")
    if len(results) > 5:
        suggestions.append("narrow down results")

    if suggestions:
        return f"Would you like to {' or '.join(suggestions[:2])}?"

    return "You can refine these results or start a new search."


def generate_match_reason(product: dict, filters: dict) -> str:
    """Generate explanation for why a product matched."""
    reasons = []

    if filters.get("brand") and product.get("brand", "").lower() == filters["brand"].lower():
        reasons.append(f"{filters['brand']} brand")

    if filters.get("price_max") and product.get("price", 0) <= filters["price_max"]:
        reasons.append(f"under ₹{filters['price_max']}")

    if filters.get("category"):
        reasons.append(f"in {filters['category']}")

    if filters.get("attributes"):
        matching_attrs = [
            attr for attr in filters["attributes"]
            if attr.lower() in [a.lower() for a in product.get("attributes", [])]
        ]
        if matching_attrs:
            reasons.append(", ".join(matching_attrs))

    if not reasons:
        return "Matches your search query"

    return "Matches " + ", ".join(reasons)
