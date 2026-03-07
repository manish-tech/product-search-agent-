from typing import List, Optional, Union


class EmbeddingService:
    """Wrapper for sentence-transformers embedding model."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.dimension = 384  # all-MiniLM-L6-v2 output dimension

    def encode(self, text: Union[str, List[str]]):
        """Encode text(s) into vector embeddings."""
        import numpy as np
        return self.model.encode(text, normalize_embeddings=True)

    def encode_for_qdrant(self, text: str) -> List[float]:
        """Encode text and return as list for Qdrant compatibility."""
        embedding = self.encode(text)
        return embedding.tolist()


# Singleton instance
_embedder: Optional[EmbeddingService] = None


def get_embedder() -> EmbeddingService:
    """Get or create the singleton embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingService()
    return _embedder
