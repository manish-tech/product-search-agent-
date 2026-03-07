from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# --- Search Models ---

class SearchRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant identifier for multi-tenancy")
    session_id: str = Field(..., description="Client-generated UUID for session tracking")
    message: str = Field(..., description="Natural language search query")


class InterpretedFilters(BaseModel):
    category: Optional[str] = None
    brand: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    size: Optional[str] = None
    color: Optional[str] = None
    attributes: list[str] = Field(default_factory=list)


class ProductResult(BaseModel):
    sku: str
    name: str
    price: float
    score: float
    reason: str


class SearchResponse(BaseModel):
    session_id: str
    interpreted_filters: InterpretedFilters
    results: list[ProductResult]
    follow_up_hint: Optional[str] = None


# --- Ingest Models ---

class ProductIngestRequest(BaseModel):
    tenant_id: str
    sku: str
    name: str
    category: str
    brand: str
    price: float
    size: list[str] = Field(default_factory=list)
    color: Optional[str] = None
    attributes: list[str] = Field(default_factory=list)
    description: Optional[str] = None


class ProductIngestResponse(BaseModel):
    sku: str
    status: str
    collection: str


class BulkIngestRequest(BaseModel):
    tenant_id: str
    products: list[ProductIngestRequest]


class BulkIngestError(BaseModel):
    sku: str
    reason: str


class BulkIngestResponse(BaseModel):
    ingested: int
    failed: int
    errors: list[BulkIngestError] = Field(default_factory=list)


# --- Session Models ---

class Session(BaseModel):
    session_id: str
    tenant_id: str
    filters: dict = Field(default_factory=dict)
    last_result_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)


# --- Health Check ---

class HealthResponse(BaseModel):
    status: str = "ok"


# --- Filter Extraction Models (for LLM response parsing) ---

class ExtractedFilters(BaseModel):
    category: Optional[str] = None
    brand: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    size: Optional[str] = None
    color: Optional[str] = None
    attributes: list[str] = Field(default_factory=list)
    exclude_brands: list[str] = Field(default_factory=list)
    semantic_query: str = ""
