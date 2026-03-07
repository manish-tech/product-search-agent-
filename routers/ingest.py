from typing import List

from fastapi import APIRouter, HTTPException

from models.schemas import (
    ProductIngestRequest,
    ProductIngestResponse,
    BulkIngestRequest,
    BulkIngestResponse,
    BulkIngestError
)
from services.qdrant_service import get_qdrant_service


router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


@router.post("/product", response_model=ProductIngestResponse)
async def ingest_product(request: ProductIngestRequest):
    """
    Ingest a single product into the tenant's collection.
    """
    qdrant = get_qdrant_service()

    try:
        qdrant.upsert_product(
            tenant_id=request.tenant_id,
            sku=request.sku,
            name=request.name,
            category=request.category,
            brand=request.brand,
            price=request.price,
            size=request.size,
            color=request.color,
            attributes=request.attributes,
            description=request.description
        )

        return ProductIngestResponse(
            sku=request.sku,
            status="ingested",
            collection=f"{request.tenant_id}_products"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/products/bulk", response_model=BulkIngestResponse)
async def ingest_products_bulk(request: BulkIngestRequest):
    """
    Ingest multiple products in bulk (max 500 per call).
    """
    if len(request.products) > 500:
        raise HTTPException(
            status_code=400,
            detail="Maximum 500 products per bulk request"
        )

    qdrant = get_qdrant_service()

    ingested = 0
    failed = 0
    errors: List[BulkIngestError] = []

    for product in request.products:
        try:
            # Validate required fields
            if not product.name:
                raise ValueError("missing name field")
            if not product.sku:
                raise ValueError("missing sku field")

            qdrant.upsert_product(
                tenant_id=request.tenant_id,
                sku=product.sku,
                name=product.name,
                category=product.category,
                brand=product.brand,
                price=product.price,
                size=product.size,
                color=product.color,
                attributes=product.attributes,
                description=product.description
            )
            ingested += 1

        except Exception as e:
            failed += 1
            errors.append(BulkIngestError(
                sku=product.sku if product.sku else "unknown",
                reason=str(e)
            ))

    return BulkIngestResponse(
        ingested=ingested,
        failed=failed,
        errors=errors
    )


@router.get("/collection/{tenant_id}")
async def get_collection_info(tenant_id: str):
    """
    Get information about a tenant's product collection.
    """
    qdrant = get_qdrant_service()
    info = qdrant.get_collection_info(tenant_id)

    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Collection not found for tenant: {tenant_id}"
        )

    return info


@router.delete("/product/{tenant_id}/{sku}")
async def delete_product(tenant_id: str, sku: str):
    """
    Delete a product from the tenant's collection.
    """
    qdrant = get_qdrant_service()

    try:
        qdrant.delete_product(tenant_id=tenant_id, sku=sku)
        return {"status": "deleted", "sku": sku}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
