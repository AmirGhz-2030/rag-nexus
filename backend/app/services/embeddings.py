from typing import List
from sentence_transformers import SentenceTransformer
from app.core.config import settings

class EmbeddingService:
    """Vector embedding generator using HuggingFace SentenceTransformers."""

    def __init__(self, model_name: str = settings.EMBEDDING_MODEL_NAME):
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        if self._model is None:
            # Lazy load model on demand
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding vector for a single string."""
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for a batch of strings."""
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()
