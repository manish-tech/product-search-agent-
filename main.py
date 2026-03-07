import os
import threading
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


# Load environment variables
load_dotenv()

# Track whether startup initialization is complete
_ready = False


def _background_init():
    """Heavy initialization in background thread so the port binds fast."""
    global _ready

    print("Initializing embedding service...")
    from services.embedder import get_embedder
    get_embedder()
    print("Embedding service ready (using HuggingFace API).")

    print("Initializing Qdrant service...")
    from services.qdrant_service import get_qdrant_service
    get_qdrant_service()
    print("Qdrant service initialized.")

    from services.session_store import get_session_store
    get_session_store()
    print("Session store initialized.")

    print("Ingesting product catalog...")
    from scripts.ingest_catalog import generate_products
    qdrant = get_qdrant_service()
    products = generate_products()[:50]
    tenant_id = "retailer_abc"
    try:
        count = qdrant.upsert_products_batch(tenant_id, products)
        print(f"Ingested {count} products.")
    except Exception as e:
        print(f"Batch ingest failed: {e}, falling back to individual ingest...")
        success = 0
        for p in products:
            try:
                qdrant.upsert_product(
                    tenant_id=tenant_id,
                    sku=p["sku"], name=p["name"], category=p["category"],
                    brand=p["brand"], price=p["price"], size=p["size"],
                    color=p["color"], attributes=p["attributes"],
                    description=p["description"]
                )
                success += 1
            except Exception as e2:
                print(f"  Failed: {p['sku']} - {e2}")
        print(f"Ingested {success}/{len(products)} products.")

    # Register routers after init is complete
    from routers.ingest import router as ingest_router
    from routers.search import router as search_router
    app.include_router(search_router)
    app.include_router(ingest_router)

    _ready = True
    print("Product Search Agent ready!")


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    print("Starting Product Search Agent...")
    init_thread = threading.Thread(target=_background_init, daemon=True)
    init_thread.start()

    yield

    print("Shutting down Product Search Agent...")
    try:
        from observability.langfuse_client import shutdown as shutdown_langfuse
        shutdown_langfuse()
    except Exception:
        pass
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/ready")
async def readiness_check():
    """Readiness check — returns 503 until initialization is complete."""
    if not _ready:
        return JSONResponse(status_code=503, content={"status": "initializing"})
    return {"status": "ready"}


@app.get("/")
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
