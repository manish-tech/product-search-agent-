from langgraph.graph import StateGraph, END

from agent.state import SearchState
from agent.nodes import (
    load_session,
    extract_filters,
    merge_filters,
    hybrid_search,
    rerank_results,
    save_session,
    build_response
)


def create_search_graph() -> StateGraph:
    """Create and compile the LangGraph search agent."""

    # Initialize the graph with our state schema
    graph = StateGraph(SearchState)

    # Add nodes
    graph.add_node("load_session", load_session)
    graph.add_node("extract_filters", extract_filters)
    graph.add_node("merge_filters", merge_filters)
    graph.add_node("hybrid_search", hybrid_search)
    graph.add_node("rerank", rerank_results)
    graph.add_node("save_session", save_session)
    graph.add_node("build_response", build_response)

    # Define the flow
    graph.set_entry_point("load_session")

    graph.add_edge("load_session", "extract_filters")
    graph.add_edge("extract_filters", "merge_filters")
    graph.add_edge("merge_filters", "hybrid_search")
    graph.add_edge("hybrid_search", "rerank")
    graph.add_edge("rerank", "save_session")
    graph.add_edge("save_session", "build_response")
    graph.add_edge("build_response", END)

    # Compile the graph
    return graph.compile()


# Singleton compiled graph
_search_graph = None


def get_search_graph():
    """Get or create the singleton search graph."""
    global _search_graph
    if _search_graph is None:
        _search_graph = create_search_graph()
    return _search_graph


async def run_search(
    tenant_id: str,
    session_id: str,
    user_message: str,
    trace=None
) -> dict:
    """
    Run the search agent with the given inputs.

    Args:
        tenant_id: Tenant identifier
        session_id: Session identifier
        user_message: User's natural language query
        trace: Optional Langfuse trace object

    Returns:
        Dict with search results and metadata
    """
    graph = get_search_graph()

    # Initialize state
    initial_state: SearchState = {
        "tenant_id": tenant_id,
        "session_id": session_id,
        "user_message": user_message,
        "session": {},
        "extracted_filters": {},
        "merged_filters": {},
        "raw_results": [],
        "final_results": [],
        "follow_up_hint": "",
        "interpreted_filters": {},
        "error": None,
        "trace": trace
    }

    # Run the graph
    final_state = await graph.ainvoke(initial_state)

    return {
        "session_id": session_id,
        "interpreted_filters": final_state.get("interpreted_filters", {}),
        "results": final_state.get("final_results", []),
        "follow_up_hint": final_state.get("follow_up_hint", ""),
        "error": final_state.get("error")
    }
