import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models.schemas import HealthResponse
from routers.ingest import router as ingest_router
from routers.search import router as search_router
from observability.langfuse_client import shutdown as shutdown_langfuse


# Load environment variables
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle.
    - Startup: Initialize services
    - Shutdown: Cleanup resources
    """
    # Startup
    print("Starting Product Search Agent...")

    # Pre-load embedding model (takes a few seconds on first load)
    print("Loading embedding model...")
    from services.embedder import get_embedder
    get_embedder()
    print("Embedding model loaded.")

    # Initialize Qdrant service
    print("Initializing Qdrant service...")
    from services.qdrant_service import get_qdrant_service
    get_qdrant_service()
    print("Qdrant service initialized.")

    # Initialize session store
    from services.session_store import get_session_store
    get_session_store()
    print("Session store initialized.")

    # Ingest sample catalog into in-memory Qdrant
    print("Ingesting product catalog...")
    from scripts.ingest_catalog import generate_products
    qdrant = get_qdrant_service()
    products = generate_products()
    tenant_id = "retailer_abc"
    qdrant.ensure_collection(tenant_id)
    success = 0
    for p in products:
        try:
            qdrant.upsert_product(
                tenant_id=tenant_id,
                sku=p["sku"],
                name=p["name"],
                category=p["category"],
                brand=p["brand"],
                price=p["price"],
                size=p["size"],
                color=p["color"],
                attributes=p["attributes"],
                description=p["description"]
            )
            success += 1
        except Exception as e:
            print(f"  Failed: {p['sku']} - {e}")
    print(f"Ingested {success}/{len(products)} products.")

    print("Product Search Agent ready!")

    yield

    # Shutdown
    print("Shutting down Product Search Agent...")
    shutdown_langfuse()
    print("Shutdown complete.")


# Create FastAPI app
app = FastAPI(
    title="Product Search Agent",
    description="Conversational product search API with natural language understanding",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(search_router)
app.include_router(ingest_router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="ok")


@app.get("/", tags=["root"])
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Product Search Agent",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True
    )
