import os
from typing import List, Optional
from huggingface_hub import InferenceClient


HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingService:
    """Embeddings via HuggingFace Inference API (free with token)."""

    def __init__(self):
        hf_token = os.getenv("HF_TOKEN")
        self.client = InferenceClient(token=hf_token)
        self.model = HF_MODEL
        self.dimension = 384

    def encode_for_qdrant(self, text: str) -> List[float]:
        """Encode text and return as list for Qdrant compatibility."""
        result = self.client.feature_extraction(text, model=self.model)
        # Result shape is (1, seq_len, 384) — mean pool to get (384,)
        import numpy as np
        arr = np.array(result)
        if arr.ndim == 3:
            embedding = arr[0].mean(axis=0)
        elif arr.ndim == 2:
            embedding = arr.mean(axis=0)
        else:
            embedding = arr
        # Normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding.tolist()

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """Encode multiple texts."""
        results = []
        for text in texts:
            results.append(self.encode_for_qdrant(text))
        return results


# Singleton instance
_embedder: Optional[EmbeddingService] = None


def get_embedder() -> EmbeddingService:
    """Get or create the singleton embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingService()
    return _embedder
