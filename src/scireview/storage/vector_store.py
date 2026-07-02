from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from scireview.domain.documents import ChunkType, DocumentChunk


@dataclass(frozen=True)
class SearchResult:
    chunk: DocumentChunk
    score: float


class VectorStore(Protocol):
    def upsert_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None: ...
    def search(
        self,
        embedding: list[float],
        *,
        paper_id: str | None = None,
        section: str | None = None,
        page: int | None = None,
        chunk_type: ChunkType | None = None,
        limit: int = 10,
    ) -> list[SearchResult]: ...


class DisabledVectorStore:
    """No-op vector store used when indexing is disabled."""

    def upsert_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        return None

    def search(
        self,
        embedding: list[float],
        *,
        paper_id: str | None = None,
        section: str | None = None,
        page: int | None = None,
        chunk_type: ChunkType | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        return []


class QdrantLocalVectorStore:
    """Qdrant local-mode vector store for document chunk embeddings."""

    def __init__(self, storage_dir: Path, *, collection_name: str = "chunks") -> None:
        from qdrant_client import QdrantClient

        storage_dir.mkdir(parents=True, exist_ok=True)
        self.client = QdrantClient(path=str(storage_dir))
        self.collection_name = collection_name

    def upsert_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        from qdrant_client.http.models import Distance, PointStruct, VectorParams

        vector_size = len(embeddings[0])
        collections = {item.name for item in self.client.get_collections().collections}
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
        points = [
            PointStruct(
                id=chunk.chunk_id,
                vector=embedding,
                payload={
                    "paper_id": chunk.paper_id,
                    "section": chunk.section_title,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "chunk_type": chunk.chunk_type.value,
                    "text": chunk.text,
                },
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        self.client.upsert(collection_name=self.collection_name, points=points)

    def search(
        self,
        embedding: list[float],
        *,
        paper_id: str | None = None,
        section: str | None = None,
        page: int | None = None,
        chunk_type: ChunkType | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue, Range

        conditions = []
        if paper_id:
            conditions.append(FieldCondition(key="paper_id", match=MatchValue(value=paper_id)))
        if section:
            conditions.append(FieldCondition(key="section", match=MatchValue(value=section)))
        if chunk_type:
            conditions.append(
                FieldCondition(key="chunk_type", match=MatchValue(value=chunk_type.value))
            )
        if page:
            conditions.extend(
                [
                    FieldCondition(key="page_start", range=Range(lte=page)),
                    FieldCondition(key="page_end", range=Range(gte=page)),
                ]
            )
        query_filter = Filter(must=conditions) if conditions else None
        hits = self.client.search(
            collection_name=self.collection_name,
            query_vector=embedding,
            query_filter=query_filter,
            limit=limit,
        )
        results: list[SearchResult] = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(
                SearchResult(
                    chunk=DocumentChunk(
                        chunk_id=str(hit.id),
                        paper_id=str(payload["paper_id"]),
                        section_title=payload.get("section"),
                        page_start=int(payload["page_start"]),
                        page_end=int(payload["page_end"]),
                        text=str(payload["text"]),
                        chunk_type=ChunkType(str(payload["chunk_type"])),
                    ),
                    score=float(hit.score),
                )
            )
        return results
