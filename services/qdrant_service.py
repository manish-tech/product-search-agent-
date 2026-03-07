import hashlib
import os
from typing import List, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    VectorParams,
    Distance,
    PointStruct,
    Filter,
    FieldCondition,
    Range,
    MatchValue,
    MatchAny,
)

class QdrantService:
    """Service for interacting with Qdrant vector database."""

    def __init__(self):
        url = os.getenv("QDRANT_URL")
        api_key = os.getenv("QDRANT_API_KEY")

        if url and api_key and "your-cluster" not in url and not api_key.startswith("your_"):
            self.client = QdrantClient(url=url, api_key=api_key)
        else:
            # Local in-memory Qdrant for development
            self.client = QdrantClient(":memory:")

        from services.embedder import get_embedder
        self.embedder = get_embedder()
        self.vector_size = 384  # all-MiniLM-L6-v2 dimension

    def _get_collection_name(self, tenant_id: str) -> str:
        """Generate collection name for a tenant."""
        return f"{tenant_id}_products"

    def ensure_collection(self, tenant_id: str) -> None:
        """Create collection if it doesn't exist."""
        collection_name = self._get_collection_name(tenant_id)

        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]

        if collection_name not in collection_names:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE
                )
            )

    def upsert_product(
        self,
        tenant_id: str,
        sku: str,
        name: str,
        category: str,
        brand: str,
        price: float,
        size: List[str],
        color: Optional[str],
        attributes: List[str],
        description: Optional[str]
    ) -> None:
        """
        Upsert a single product into the tenant's collection.
        """
        self.ensure_collection(tenant_id)
        collection_name = self._get_collection_name(tenant_id)

        # Create embedding from name + description + attributes
        text_to_embed = f"{name} {category} {' '.join(attributes)}"
        if description:
            text_to_embed += f" {description}"

        vector = self.embedder.encode_for_qdrant(text_to_embed)

        # Use SKU hash as point ID
        point_id = int(hashlib.sha256(sku.encode()).hexdigest()[:16], 16)

        payload = {
            "sku": sku,
            "name": name,
            "category": category.lower(),
            "brand": brand.lower(),
            "price": price,
            "size": size,
            "color": color.lower() if color else None,
            "attributes": [attr.lower() for attr in attributes],
            "description": description
        }

        self.client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload
                )
            ]
        )

    def upsert_products_batch(self, tenant_id: str, products: List[dict]) -> int:
        """Upsert products in batch with batched embedding API calls."""
        self.ensure_collection(tenant_id)
        collection_name = self._get_collection_name(tenant_id)

        # Prepare texts for batch embedding
        texts = []
        for p in products:
            text = f"{p['name']} {p['category']} {' '.join(p.get('attributes', []))}"
            if p.get('description'):
                text += f" {p['description']}"
            texts.append(text)

        # Batch embed (chunks of 32 to avoid API limits)
        all_vectors = []
        for i in range(0, len(texts), 32):
            batch = texts[i:i + 32]
            vectors = self.embedder.encode_batch(batch)
            all_vectors.extend(vectors)

        # Build points
        points = []
        for p, vector in zip(products, all_vectors):
            point_id = int(hashlib.sha256(p['sku'].encode()).hexdigest()[:16], 16)
            payload = {
                "sku": p['sku'],
                "name": p['name'],
                "category": p['category'].lower(),
                "brand": p['brand'].lower(),
                "price": p['price'],
                "size": p.get('size', []),
                "color": p.get('color', '').lower() if p.get('color') else None,
                "attributes": [a.lower() for a in p.get('attributes', [])],
                "description": p.get('description')
            }
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        # Upsert in chunks of 100
        for i in range(0, len(points), 100):
            self.client.upsert(
                collection_name=collection_name,
                points=points[i:i + 100]
            )

        return len(points)

    def build_filter(self, filters: dict) -> Optional[Filter]:
        """
        Build Qdrant filter from extracted filters dict.
        """
        conditions = []

        # Category filter
        if filters.get("category"):
            conditions.append(
                FieldCondition(
                    key="category",
                    match=MatchValue(value=filters["category"].lower())
                )
            )

        # Brand filter
        if filters.get("brand"):
            conditions.append(
                FieldCondition(
                    key="brand",
                    match=MatchValue(value=filters["brand"].lower())
                )
            )

        # Price range filter
        price_range = {}
        if filters.get("price_min") is not None:
            price_range["gte"] = filters["price_min"]
        if filters.get("price_max") is not None:
            price_range["lte"] = filters["price_max"]

        if price_range:
            conditions.append(
                FieldCondition(
                    key="price",
                    range=Range(**price_range)
                )
            )

        # Size filter
        if filters.get("size"):
            conditions.append(
                FieldCondition(
                    key="size",
                    match=MatchAny(any=[filters["size"]])
                )
            )

        # Color filter
        if filters.get("color"):
            conditions.append(
                FieldCondition(
                    key="color",
                    match=MatchValue(value=filters["color"].lower())
                )
            )

        # Attributes filter (match any)
        if filters.get("attributes"):
            for attr in filters["attributes"]:
                conditions.append(
                    FieldCondition(
                        key="attributes",
                        match=MatchAny(any=[attr.lower()])
                    )
                )

        # Exclude brands filter (must_not)
        must_not_conditions = []
        if filters.get("exclude_brands"):
            for brand in filters["exclude_brands"]:
                must_not_conditions.append(
                    FieldCondition(
                        key="brand",
                        match=MatchValue(value=brand.lower())
                    )
                )

        if not conditions and not must_not_conditions:
            return None

        return Filter(
            must=conditions if conditions else None,
            must_not=must_not_conditions if must_not_conditions else None
        )

    def search(
        self,
        tenant_id: str,
        query: str,
        filters: dict,
        limit: int = 10
    ) -> List[dict]:
        """
        Perform hybrid search: vector similarity + metadata filters.

        Args:
            tenant_id: Tenant identifier
            query: Semantic query string
            filters: Extracted filters dict
            limit: Maximum number of results

        Returns:
            List of product dicts with scores
        """
        collection_name = self._get_collection_name(tenant_id)

        # Check if collection exists
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        if collection_name not in collection_names:
            return []

        # Embed the query
        query_vector = self.embedder.encode_for_qdrant(query)

        # Build filter
        qdrant_filter = self.build_filter(filters)

        # Search using query_points (qdrant-client >= 1.12)
        results = self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=qdrant_filter,
            limit=limit,
            with_payload=True
        )

        # Format results
        products = []
        for hit in results.points:
            product = hit.payload.copy()
            product["score"] = hit.score
            products.append(product)

        return products

    def delete_product(self, tenant_id: str, sku: str) -> None:
        """Delete a product by SKU."""
        collection_name = self._get_collection_name(tenant_id)
        point_id = int(hashlib.sha256(sku.encode()).hexdigest()[:16], 16)

        self.client.delete(
            collection_name=collection_name,
            points_selector=models.PointIdsList(points=[point_id])
        )

    def get_collection_info(self, tenant_id: str) -> Optional[dict]:
        """Get collection info for a tenant."""
        collection_name = self._get_collection_name(tenant_id)

        try:
            info = self.client.get_collection(collection_name)
            return {
                "name": collection_name,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count
            }
        except Exception:
            return None


# Singleton instance
_qdrant_service: Optional[QdrantService] = None


def get_qdrant_service() -> QdrantService:
    """Get or create the singleton Qdrant service instance."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service
