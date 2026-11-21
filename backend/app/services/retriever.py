from typing import List, Dict, Any
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
from app.services.embeddings import EmbeddingService
from app.core.config import settings

class HybridRetriever:
    """Advanced Hybrid Retriever with BM25 + Vector Search + Cross-Encoder Reranking."""

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.documents_store: List[Dict[str, Any]] = []
        self.indexed_files: Dict[str, int] = {}  # {filename: chunk_count}
        self.bm25 = None
        self._reranker = None

    @property
    def reranker(self):
        if self._reranker is None:
            self._reranker = CrossEncoder(settings.RERANKER_MODEL_NAME)
        return self._reranker

    def add_documents(self, chunks: List[Dict[str, Any]]):
        """Index chunks into memory store and build BM25 sparse index."""
        for chunk in chunks:
            vector = self.embedding_service.embed_text(chunk["content"])
            chunk["vector"] = vector
            self.documents_store.append(chunk)

            source = chunk.get("metadata", {}).get("source", "Doc")
            self.indexed_files[source] = self.indexed_files.get(source, 0) + 1

        # Re-build BM25 index
        tokenized_corpus = [doc["content"].lower().split() for doc in self.documents_store]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def clear_documents(self):
        """Clear all indexed documents and reset sparse index."""
        self.documents_store = []
        self.indexed_files = {}
        self.bm25 = None

    def get_indexed_files(self) -> List[Dict[str, Any]]:
        """Return list of indexed file names and chunk counts."""
        return [{"filename": fn, "chunks": count} for fn, count in self.indexed_files.items()]

    def search(self, query: str, top_k: int = 5, alpha: float = 0.5) -> List[Dict[str, Any]]:
        """Hybrid Search combining Vector Cosine Similarity and BM25 Scores with Reranking."""
        if not self.documents_store:
            return []

        # 1. Sparse BM25 scoring
        tokenized_query = query.lower().split()
        bm25_scores = self.bm25.get_scores(tokenized_query) if self.bm25 else [0] * len(self.documents_store)

        # Normalize BM25 scores
        bm25_scores_list = list(bm25_scores) if hasattr(bm25_scores, '__iter__') else [0] * len(self.documents_store)
        max_bm25 = max(bm25_scores_list) if len(bm25_scores_list) > 0 and max(bm25_scores_list) > 0 else 1.0
        norm_bm25 = [score / max_bm25 for score in bm25_scores_list]

        # 2. Dense Vector Cosine Similarity
        query_vector = self.embedding_service.embed_text(query)
        import numpy as np

        vector_scores = []
        for doc in self.documents_store:
            doc_vec = np.array(doc["vector"])
            q_vec = np.array(query_vector)
            similarity = float(np.dot(doc_vec, q_vec) / (np.linalg.norm(doc_vec) * np.linalg.norm(q_vec) + 1e-9))
            vector_scores.append(similarity)

        # 3. Hybrid Score Combination
        candidates = []
        for idx, doc in enumerate(self.documents_store):
            hybrid_score = (alpha * vector_scores[idx]) + ((1 - alpha) * norm_bm25[idx])
            candidates.append({
                "doc": doc,
                "hybrid_score": hybrid_score,
                "vector_score": vector_scores[idx],
                "bm25_score": norm_bm25[idx]
            })

        # Sort candidates by hybrid score to get initial candidates
        candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)
        top_candidates = candidates[:top_k * 2]

        if not top_candidates:
            return []

        # 4. Cross-Encoder Re-ranking
        pairs = [[query, item["doc"]["content"]] for item in top_candidates]
        rerank_scores = self.reranker.predict(pairs)

        final_results = []
        for idx, item in enumerate(top_candidates):
            final_results.append({
                "id": item["doc"]["id"],
                "content": item["doc"]["content"],
                "metadata": item["doc"]["metadata"],
                "vector_score": item["vector_score"],
                "bm25_score": item["bm25_score"],
                "rerank_score": float(rerank_scores[idx])
            })

        # Sort by rerank score
        final_results.sort(key=lambda x: x["rerank_score"], reverse=True)
        return final_results[:top_k]
