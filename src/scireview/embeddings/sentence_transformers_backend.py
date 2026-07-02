from __future__ import annotations

from scireview.embeddings.base import EmbeddingBackend


class SentenceTransformersBackend(EmbeddingBackend):
    """Sentence Transformers embedding backend."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [vector.astype(float).tolist() for vector in vectors]
