from typing import Any, Dict, List, Optional, TypedDict


class SearchState(TypedDict):
    """State object that flows through the LangGraph agent."""

    # Input
    tenant_id: str
    session_id: str
    user_message: str

    # Session data
    session: dict  # Loaded session data

    # Intermediate
    extracted_filters: dict  # Filters extracted from LLM
    merged_filters: dict  # Session filters + new filters
    raw_results: List[dict]  # Results from Qdrant

    # Output
    final_results: List[dict]  # Reranked results
    follow_up_hint: str  # Suggestion for next query
    interpreted_filters: dict  # Final filters to return to client
    error: Optional[str]  # Error message if any

    # Observability
    trace: Optional[Any]  # Langfuse trace object
