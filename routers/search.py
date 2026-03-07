from fastapi import APIRouter, HTTPException

from models.schemas import (
    SearchRequest,
    SearchResponse,
    InterpretedFilters,
    ProductResult
)
from agent.graph import run_search
from observability.langfuse_client import create_trace, end_trace


router = APIRouter(prefix="/api/v1", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search_products(request: SearchRequest):
    """
    Search for products using natural language.

    Accepts a user message, extracts filters, performs hybrid search,
    and returns ranked results with explanations.
    """
    # Create Langfuse trace
    trace = create_trace(
        session_id=request.session_id,
        tenant_id=request.tenant_id,
        user_message=request.message
    )

    try:
        # Run the search agent
        result = await run_search(
            tenant_id=request.tenant_id,
            session_id=request.session_id,
            user_message=request.message,
            trace=trace
        )

        # Check for errors
        if result.get("error"):
            end_trace(trace, result, error=result["error"])
            raise HTTPException(status_code=500, detail=result["error"])

        # Build response
        interpreted = InterpretedFilters(**result.get("interpreted_filters", {}))

        results = [
            ProductResult(**r) for r in result.get("results", [])
        ]

        response = SearchResponse(
            session_id=request.session_id,
            interpreted_filters=interpreted,
            results=results,
            follow_up_hint=result.get("follow_up_hint")
        )

        # End trace with success
        end_trace(trace, {
            "num_results": len(results),
            "filters": result.get("interpreted_filters", {})
        })

        return response

    except HTTPException:
        raise
    except Exception as e:
        end_trace(trace, {"error": str(e)}, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
