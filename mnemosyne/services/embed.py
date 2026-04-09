import ollama
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from mnemosyne.config import get_settings
from mnemosyne.agent.schemas import Chunk, SearchResult
import uuid

def _qdrant() -> QdrantClient:
    return QdrantClient(url=get_settings().qdrant_host)

def _embed(text: str) -> list[float]:
    settings = get_settings()
    response = ollama.embed(model=settings.embed_model, input=text)
    return response.embeddings

def ensure_collection(dim: int = 768):
    client = _qdrant()
    settings = get_settings()
    existing = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

def index_chunks(chunks: list[Chunk], batch_size: int = 50):
    settings = get_settings()
    client = _qdrant()
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        points = []
        for chunk in batch:
            vector = _embed(chunk.text)
            points.append(PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.id)),
                vector=vector,
                payload={
                    "chunk_id": chunk.id,
                    "note_path": chunk.note_path,
                    "note_title": chunk.note_title,
                    "heading": chunk.heading,
                    "text": chunk.text,
                    "tags": chunk.tags,
                }
            ))
        client.upsert(collection_name=settings.qdrant_collection, points=points)

def semantic_search(query: str, limit: int = 5) -> list[SearchResult]:
    settings = get_settings()
    client = _qdrant()
    query_vector = _embed(query)
    hits = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        limit=limit,
        with_payload=True,
    )
    return [
        SearchResult(
            chunk_id=hit.payload["chunk_id"],
            note_path=hit.payload["note_path"],
            note_title=hit.payload["note_title"],
            heading=hit.payload["heading"],
            excerpt=hit.payload["text"][:200].replace("\n", " "),
            score=hit.score,
            source="semantic",
        )
        for hit in hits
    ]
