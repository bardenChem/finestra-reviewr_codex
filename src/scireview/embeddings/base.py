from __future__ import annotations

from typing import Protocol


class EmbeddingBackend(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts into dense vectors."""
